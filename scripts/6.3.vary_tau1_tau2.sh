#!/bin/bash
######################################################################
#6.3.VARY_TAU1_TAU2 ---

# Search a best TAU1 and TAU2

# Author: Zi Liang <zi1415926.liang@connect.polyu.hk>
# Copyright © 2024, ZiLiang, all rights reserved.
# Created: 14 May 2024
######################################################################

######################### Commentary ##################################
##  
######################################################################

echo "HOME: ${HOME}"
export python=${HOME}/anaconda3/envs/align/bin/python3
export CUDA_VISIBLE_DEVICES="0"
# export CUDA_VISIBLE_DEVICES="4,5,6"
# export CUDA_VISIBLE_DEVICES="3,6,7"
export TORCH_USE_CUDA_DSA="1"
export root_dir="${HOME}/alignmentExtraction/"
export POD_save_dir="${root_dir}/qa_ckpts/"
export from_path="meta-llama/Meta-Llama-3-8B-Instruct"
# export from_path="google/gemma-7b"
# export TRAIN_NUMS=(64 128 256 512)
export TRAIN_NUMS=(64)
# export train_times=(1 2 3 4 5)
export train_times=(1)
export msl=256
# export task_ls=("piqa" "truthful_qa" "allenai/ai2_arc")
# export task_ls=("piqa")
# export task_ls=("cs-en" "de-en" "fi-en")
export task_ls=("cs-en")
export train_taskls=("LoRD-VI")
# export train_taskls=("LoRD-VI" "vanilla")

export is_black_box=1
export use_lora=1

# export epoch=3
# export period=3

export epoch=2
export period=1

export sub_set_num=1
export sub_stage_num=512
# export sub_stage_num=16
export max_new_tokens=64
export infer_batch_size=1
export batch_size=1

export beta=-1
export temperature=-1

export use_old_logits=1
export use_vic_logits=1
export use_kld=0
export use_entropy=0

# export tau1_list=(0.70 0.75 0.80 0.85 0.90 0.95 1.0)
export tau1_list=(0.4 0.5 0.6)
export tau2_list=(1.0)

# export tau1=-0.1
# export tau2=0.95
# export tau2_list=(1.0)

for tau1 in ${tau1_list[*]}
do
    for tau2 in ${tau2_list[*]}
    do
for train_num in ${TRAIN_NUMS[*]}
do
    for train_time in ${train_times[*]}
    do
	for task in ${task_ls[*]}
	do
	    for train_task in ${train_taskls[*]}
	    do
		echo "====================================================="
		echo "+++++++TAU1: ${tau1}+++++++"
		echo "+++++++TAU2: ${tau2}+++++++"
		echo "+++++++train_num: ${train_num}+++++++"
		echo "+++++++train_time: ${train_time}+++++++"
		echo "+++++++task: ${task}+++++++"
		echo "+++++++train_task: ${train_task}+++++++"
		echo "====================================================="

		export save_path="${POD_save_dir}WMTTT-TAU1${tau1}TAU2${tau2}${task}${train_num}${train_time}${train_task}"

		$python ${root_dir}lord_train.py\
		    --dataset_task=$task \
		    --use_lora=$use_lora \
		    --from_path=$from_path \
		    --is_black_box=$is_black_box \
		    --sub_set_num=$sub_set_num \
		    --sub_stage_num=$sub_stage_num\
		    --infer_batch_size=$infer_batch_size\
		    --tau1=$tau1 \
		    --tau2=$tau2 \
		    --task=$train_task \
		    --device="cuda" \
		    --epoch=$epoch \
		    --period_num=$period \
		    --acc_step=1 \
		    --log_step=50 \
		    --train_num=$train_num \
		    --max_new_tokens=$max_new_tokens \
		    --LR="3e-5" \
		    --beta=$beta \
		    --temperature=$temperature \
		    --batch_size=$batch_size \
		    --use_old_logits=$use_old_logits\
		    --use_vic_logits=$use_vic_logits\
		    --use_kld=$use_kld\
		    --max_length=$msl \
		    --save_path=$save_path
		echo "DONE FOR ONE TRAIN NUMBERS...."
	    done
	done
    done
done
    done
done

echo "NOW BEGIN TO INFERENCE..."
$python ${root_dir}wmt_process.py

echo "RUNNING 6.3.vary_tau1_tau2.sh DONE."
# 6.3.vary_tau1_tau2.sh ends here
