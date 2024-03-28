"""
======================================================================
TRAIN_POD2 ---

New stealing mechamism.

    Author: Zi Liang <zi1415926.liang@connect.polyu.hk>
    Copyright © 2024, ZiLiang, all rights reserved.
    Created: 27 March 2024
======================================================================
"""


# ------------------------ Code --------------------------------------
import torch
# import json
from torch.utils.tensorboard import SummaryWriter
# from torch.distributions import Categorical
from torch.utils.data import TensorDataset, DataLoader
from tqdm import tqdm
# import argparse
# from transformers import AutoModelForCausalLM
# from transformers import AutoModelForSequenceClassification
# from transformers import AutoModelForTokenClassification
# from transformers import AutoTokenizer, AutoConfig, AutoModel

# from training_data_collecting_openai import load_raw_train_datals
# from training_data_collecting_openai import load_steal_datals
# from glue_process import load_glue_datals

from sequence_utils import my_padding, my_padding_logits
from sequence_utils import my_padding_token_dist
from sequence_utils import my_padding_logit

import torch.nn.functional as F

# from rlhf_train import clip, log_clip
import random


def random_take(num, ls):
    random.shuffle(ls)
    if num >= len(ls):
        return ls
    return ls[:num]


def train(lm, lm_tokenizer, args,
          raw_train_datals, max_new_tokens=16):
    sub_stage_num = args.sub_stage_num
    for ssn in range(sub_stage_num):
        lm = train_pod(lm, lm_tokenizer,
                       args, raw_train_datals, max_new_tokens)


def train_pod(lm,
              lm_tokenizer,
              args, raw_train_datals,
              max_new_tokens=-1,
              ):
    print(">>>> DATA PREPERATION")
    # STEP 1: DATA Preperation.
    ITER_num = args.period_num
    tb_writer = SummaryWriter(log_dir=args.save_path+"___log_writer")
    op_ls, oidx2ls, ologits2ls, oidx2_dist = raw_train_datals

    subset_num = args.sub_set_num

    # 1. in every period, random take a subset.
    p_ls = random_take(subset_num, op_ls)
    idx2ls = random_take(subset_num, oidx2ls)
    logits2ls = random_take(subset_num, ologits2ls)
    idx2_dist = random_take(subset_num, oidx2_dist)

    for iter_idx in range(ITER_num):
        tensorboard_name = f"Period {iter_idx}"

        if iter_idx == 0:
            # previous_generated_ls
            p_i_11_ls = []
            p_i_12_ls = []
            p_logits_11_ls = []
            p_logits_12_ls = []
            p_m_11_ls = []
            p_m_12_ls = []

        idxs11_ls = []
        idxs12_ls = []
        old_logits11_ls = []
        old_logits12_ls = []

        old_logits2_ls = []

        # 2. generate
        with torch.no_grad():
            for i, prompt in tqdm(enumerate(p_ls),
                                  desc="Data Collecting..."):
                prompt = prompt.to(args.device).unsqueeze(0)
                # Generate New Tokens
                idxs12 = lm.generate(prompt,
                                     do_sample=True,
                                     max_length=args.max_length,
                                     max_new_tokens=max_new_tokens,
                                     # temperature=args.temperature,
                                     )
                if iter_idx != 0:
                    idxs11 = lm.generate(prompt,
                                         do_sample=True,
                                         max_length=args.max_length,
                                         max_new_tokens=max_new_tokens,
                                         # temperature=args.temperature,
                                         )
                else:
                    # i.e., idx2
                    idxs11 = torch.tensor(idx2ls[i],
                                          dtype=torch.long)\
                        .to(args.device).unsqueeze(0)

                bs, sqqql = idxs11.shape
                # print(idxs1)
                print(lm_tokenizer.decode(idxs11[0]))
                print(lm_tokenizer.decode(idxs12[0]))
                old_logits11 = lm(idxs11[:, :-1]).logits
                old_logits11 = F.log_softmax(old_logits11, dim=-1)
                old_logits11 = old_logits11[
                    torch.arange(1).unsqueeze(1),
                    torch.arange(sqqql-1).unsqueeze(0),
                    idxs11[:, 1:sqqql]
                ]

                bs, sqqql2 = idxs12.shape
                old_logits12 = lm(idxs12[:, :-1]).logits
                old_logits12 = F.log_softmax(old_logits12, dim=-1)
                old_logits12 = old_logits12[
                    torch.arange(1).unsqueeze(1),
                    torch.arange(sqqql2-1).unsqueeze(0),
                    idxs12[:, 1:sqqql2]
                ]

                idxs2 = torch.tensor(idx2ls[i], dtype=torch.long)\
                    .to(args.device).unsqueeze(0)
                old_logits2 = lm(idxs2[:, :-1]).logits
                old_logits2 = F.log_softmax(old_logits2, dim=-1)
                bs, sql2 = idxs2.shape
                old_logits2 = old_logits2[
                    torch.arange(1).unsqueeze(1),
                    torch.arange(sql2-1).unsqueeze(0),
                    idxs2[:, 1:sql2]
                ]

                idxs11_ls.append(idxs11.squeeze(0).to("cpu"))
                idxs12_ls.append(idxs12.squeeze(0).to("cpu"))
                old_logits11_ls.append(old_logits11
                                       .squeeze(0).to("cpu"))
                old_logits12_ls.append(old_logits12
                                       .squeeze(0).to("cpu"))
                old_logits2_ls.append(old_logits2.squeeze(0).to("cpu"))

                # obtain old generated text
                if iter_idx == 0:
                    p_i_11_ls.append(idxs11.squeeze(0).to("cpu"))
                    p_i_12_ls.append(idxs12.squeeze(0).to("cpu"))
                    p_logits_11_ls.append(old_logits11
                                          .squeeze(0).to("cpu"))
                    p_logits_12_ls.append(old_logits12
                                          .squeeze(0).to("cpu"))
                else:
                    pidx11 = p_i_11_ls[i].unsqueeze(0).to(args.device)
                    pidx12 = p_i_12_ls[i].unsqueeze(0).to(args.device)
                    llh1 = lm(pidx11, labels=pidx11).loss
                    llh2 = lm(pidx12, labels=pidx12).loss
                    if llh2 < llh1:
                        p_i_11_ls[i] = pidx12.squeeze(0).to("cpu")
                        p_i_12_ls[i] = pidx11.squeeze(0).to("cpu")

                        temppp = p_logits_11_ls[i]
                        p_logits_11_ls[i] = p_logits_12_ls[i]
                        p_logits_12_ls[i] = temppp

                        temppp = p_m_11_ls[i]
                        p_m_11_ls[i] = p_m_12_ls[i]
                        p_m_12_ls[i] = temppp

        # do truncations and paddings.
        max_token_num_11 = min(args.max_length,
                               max([len(x) for x in p_i_11_ls]))
        max_token_num_12 = min(args.max_length,
                               max([len(x) for x in p_i_12_ls]))
        max_token_num_2 = min(args.max_length,
                              max([len(x) for x in idx2ls]))

        cmax_token_num_11 = min(args.max_length,
                                max([len(x) for x in idxs11_ls]))
        cmax_token_num_12 = min(args.max_length,
                                max([len(x) for x in idxs12_ls]))

        max_token_num = max(max_token_num_11, max_token_num_12)
        max_token_num = max(max_token_num, max_token_num_2)
        max_token_num = max(max_token_num, cmax_token_num_11)
        max_token_num = max(max_token_num, cmax_token_num_12)

        print("max_token_num", max_token_num)
        pad_idx = lm_tokenizer.pad_token_id

        idx2ls, mask2 = my_padding(idx2ls, p_ls, max_token_num, pad_idx)
        idxs11_ls, mask11 = my_padding(idxs11_ls,
                                       p_ls, max_token_num, pad_idx)
        idxs12_ls, mask12 = my_padding(idxs12_ls,
                                       p_ls, max_token_num, pad_idx)

        old_logits11_ls = my_padding_logit(old_logits11_ls,
                                           max_token_num-1, pad_idx)
        old_logits12_ls = my_padding_logit(old_logits12_ls,
                                           max_token_num-1, pad_idx)
        old_logits2_ls = my_padding_logit(old_logits2_ls,
                                          max_token_num-1, pad_idx)
        if iter_idx == 0:
            p_i_11_ls, p_m_11_ls = my_padding(p_i_11_ls,
                                              p_ls,
                                              max_token_num, pad_idx)
            p_i_12_ls, p_m_12_ls = my_padding(p_i_12_ls,
                                              p_ls,
                                              max_token_num, pad_idx)

            p_logits_11_ls = my_padding_logit(p_logits_11_ls,
                                              max_token_num-1,
                                              pad_idx)
            p_logits_12_ls = my_padding_logit(p_logits_12_ls,
                                              max_token_num-1,
                                              pad_idx)

        newlogits2ls = []
        for per_data in logits2ls:
            sl = len(per_data)
            v = len(per_data[0])
            tmp_ts = torch.ones((sl, v), dtype=torch.float)
            for jjjj, per_token_logit in enumerate(per_data):
                tmp_ts[jjjj] = torch.tensor(per_token_logit,)
            newlogits2ls.append(tmp_ts)

        logits2ls = my_padding_logits(newlogits2ls,
                                      max_token_num-1, pad_idx)
        idxs2_dist = my_padding_token_dist(idx2_dist,
                                           max_token_num-1, pad_idx)

        print(old_logits11_ls.shape)
        trainset = TensorDataset(
            p_i_11_ls,
            p_i_12_ls,
            idx2ls,
            p_m_11_ls,
            p_m_12_ls,
            mask2,
            p_logits_11_ls,
            p_logits_12_ls,
            old_logits2_ls,
            logits2ls,
            idxs2_dist,
        )
        p_i_11_ls = idxs11_ls
        p_i_12_ls = idxs12_ls
        p_m_11_ls = mask11
        p_m_12_ls = mask12
        p_logits_11_ls = old_logits11_ls
        p_logits_12_ls = old_logits12_ls

        loader = DataLoader(trainset,
                            batch_size=args.batch_size,
                            shuffle=True,
                            )
        print(">>>> Period {}".format(iter_idx))
        if args.task == "LoRD-II":
            lm = one_period(args, lm,
                            lm_tokenizer,
                            loader,
                            args.epoch, args.device,
                            tb_writer,
                            tensorboard_name,
                            args.save_path,
                            args.LR,
                            args.acc_step, args.log_step,
                            args.save_step,
                            args.beta,
                            is_black_box=0,
                            method="lord_ii"
                            )
        else:
            print("ERROR: CANNOT FIND THE TRAIN LOSS OF THE TASK.")

        if iter_idx >= 0:
            print(" -->NOW save the ckpt in each period.")
            print(f"in period {iter_idx}.")
            # lm_tokenizer.save_pretrained(args.save_path +
            #                              "___period"+str(iter_idx))
            # lm.save_pretrained(args.save_path +
            #                    "___period"+str(iter_idx))

    print(" -->ALL TRAINING DONE.")
    # lm_tokenizer.save_pretrained(args.save_path+"___finally")
    # lm.save_pretrained(args.save_path+"___finally")
    print(" -->Save DONE.")
    return lm


def one_period(args, lm,
               lm_tokenizer,
               loader, epoch, device,
               tb_writer,
               tensorboard_name,
               save_path,
               LR=3e-5,
               acc_step=1,
               log_step=100,
               save_step=1000,
               beta=0.7,
               epsln=1e-6,
               is_black_box=0,
               method="lord_ii",
               ):

    overall_loss = 0.
    overall_step = 0
    pad_token_id = lm_tokenizer.pad_token_id
    kl_loss = torch.nn.KLDivLoss(reduction="none")
    sigmoid = torch.nn.Sigmoid()

    opt1 = torch.optim.AdamW(lm.parameters(), lr=LR)

    for e in tqdm(range(epoch), desc="epoch"):
        for item in tqdm(loader, desc="loader"):
            overall_step += 1

            # print(item)
            idxs11, idxs12, idxs2, mask11, mask12,\
                mask2, old_logits11, old_logits12,\
                old_logits2, vic_logits2, idxs2_dist = item

            bs, sqlen1 = idxs11.shape
            sqlen = sqlen1

            idxs11 = idxs11.to(device)  # bs, sql
            idxs12 = idxs12.to(device)  # bs, sql

            idxs2 = idxs2.to(device)  # bs, sql
            mask11 = mask11.to(device)
            mask12 = mask12.to(device)
            mask2 = mask2.to(device)

            # already normalized by softmax
            old_logits11 = old_logits11.to(device)  # bs, sql,
            old_logits12 = old_logits12.to(device)  # bs, sql,
            old_logits2 = old_logits2.to(device)  # bs, sql,

            vic_logits2 = vic_logits2.to(device)  # bs, sql, 5
            idxs2_dist = idxs2_dist.to(device)

            print("===========================================")
            print("idx11text: ", lm_tokenizer.decode(idxs11[0]))
            print("idx12text: ", lm_tokenizer.decode(idxs11[0]))
            print("idx2text: ", lm_tokenizer.decode(idxs2[0]))

            logits11 = lm(idxs11).logits[:, :-1, :]
            logits11 = F.log_softmax(logits11, dim=-1)
            logits11 = logits11[torch.arange(bs).unsqueeze(1),
                                torch.arange(sqlen-1).unsqueeze(0),
                                idxs11[:, 1:sqlen]]

            logits12 = lm(idxs12).logits[:, :-1, :]
            logits12 = F.log_softmax(logits12, dim=-1)
            logits12 = logits12[torch.arange(bs).unsqueeze(1),
                                torch.arange(sqlen-1).unsqueeze(0),
                                idxs12[:, 1:sqlen]]

            # logits2 = lm(idxs2).logits[:, :-1, :]
            # logits2 = torch.log_softmax(logits2, dim=-1)
            # logits2_cons = logits2[torch.arange(bs).unsqueeze(1),
            #                        torch.arange(sqlen-1).unsqueeze(0),
            #                        idxs2[:, 1:sqlen]]

            # logits2_dist = torch.gather(logits2, 2, idxs2_dist)

            # now compute the loss:
            loss = -1*(torch.sum(logits11*mask11[:, :-1])
                       / torch.sum(mask11[:, :-1])
                       - torch.sum(logits12*mask12[:, :-1]))\
                / torch.sum(mask11[:, :-1])

            overall_loss = loss
            if overall_step % log_step == 0:
                print(" LOSS: {}".format(
                    overall_loss,
                ))
                tb_writer.add_scalar("loss", overall_loss,
                                     overall_step)

            if overall_step % save_step == 0:
                print(" -->Regular Saving.")
                print(f"in epoch {e}, step {overall_step}.")
                lm_tokenizer.save_pretrained(save_path+"___"+str(overall_step))
                lm.save_pretrained(save_path+"___"+str(overall_step))

            if overall_step % acc_step == 0:
                opt1.zero_grad()

                overall_loss.backward()
                opt1.step()
                overall_loss = 0.

    print(" -->Finally Saving.")
    # lm_tokenizer.save_pretrained(save_path+"___STEPfinally")
    # lm.save_pretrained(save_path+"___STEPfinally")

    print("ONE PERIOD TRAINING DONE!")
    return lm


# running entry
if __name__ == "__main__":
    # main()
    print("EVERYTHING DONE.")
