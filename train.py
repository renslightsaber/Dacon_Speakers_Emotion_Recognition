import re
import os
import gc
import time
import random
import string

import copy
from copy import deepcopy

import torchmetrics

import numpy as np
import pandas as pd

import matplotlib.pyplot as plt

from sklearn.model_selection import GroupKFold

## Pytorch Import
import torch 
import torch.nn as nn

from torch.optim import lr_scheduler
from torch.utils.data import Dataset, DataLoader

## Transforemr Import
from transformers import AutoTokenizer, AutoModel, AdamW, AutoConfig, DataCollatorWithPadding

# Utils
from tqdm.auto import tqdm, trange

# For colored terminal text
from colorama import Fore, Back, Style
b_ = Fore.BLUE
y_ = Fore.YELLOW
sr_ = Style.RESET_ALL

# Suppress warnings
import warnings
warnings.filterwarnings("ignore")

# For descriptive error messages
os.environ['CUDA_LAUNCH_BLOCKING'] = "1"


from dataloader import *
from new_trainer import *
from model import *
from utils import *


def define():
    p = argparse.ArgumentParser()

    p.add_argument('--base_path', type = str, default = "./data/", help="Data Folder Path")
    p.add_argument('--model_save', type = str, default = "./models/", help="Data Folder Path")
    p.add_argument('--sub_path', type = str, default = "./submission/", help="Data Folder Path")
    
    p.add_argument('--n_folds', type = int, default = 5, help="Folds")
    p.add_argument('--n_epochs', type = int, default = 5, help="Epochs")
    
    p.add_argument('--seed', type = int, default = 2022, help="Seed")
    p.add_argument('--train_bs', type = int, default = 16, help="Train Batch Size")
    p.add_argument('--valid_bs', type = int, default = 16, help="Valid Batch Size")
    
    p.add_argument('--max_length', type = int, default = 256, help="Max Length")
    
    p.add_argument('--ratio', type = float, default = 0.7, help="Ratio of Train, Valid")
    
    p.add_argument('--T_max', type = int, default = 500, help="T_max")
    p.add_argument('--learning_rate', type = float, default = 1e-5, help="lr")
    p.add_argument('--min_lr', type = float, default = 1e-6, help="Min LR")
    p.add_argument('--weight_decay', type = float, default = 1e-6, help="Weight Decay")

    p.add_argument('--grad_clipping', type = bool, default = False, help="Gradient Clipping")
    p.add_argument('--device', type = str, default = "cuda", help="CUDA or MPS or CPU?")

    config = p.parse_args()
    return config
  
  
def main(config):
    
    ## Data
    train, test, ss = dacon_competition_data(base_path = config.base_path, add_speaker = True, make_essay_option= True)
    print("Dialogue_ID == 1")
    print(train[train.Dialogue_ID == 1])
    
    ## Set Seed
    set_seed(config.seed)
    
    ## Target Encoding
    train_encode = {v: k for k, v in enumerate(train.Target.unique())}
    train_inverse = {v: k for k, v in train_encode.items()}
    
    train['new_target'] = train.Target.apply(lambda x: train_encode[x])
    print(train.head())
    
    ## n_classes
    n_classes = train.new_target.nunique()
    print("n_classes: ", n_classes)
    
    ## Drop Unnecessary Columns 
    train.drop(['ID', 'Utterance', 'Speaker', 'Target', ], axis =1, inplace = True)
    print(train.shape)
    print(train.head())
    
    test.drop(['ID', 'Utterance', 'Speaker',], axis =1, inplace = True)
    print(test.shape)
    print(test.head())
    
    ### K Fold
    skf = GroupKFold(n_splits = config.n_folds)
    # skf = StratifiedGroupKFold(n_splits = config['n_folds'])
    # skf =  LeavePGroupsOut(n_groups = 1038 - 24)

    for fold, ( _, val_) in enumerate(skf.split(X=train, groups = train.Dialogue_ID)):
        train.loc[val_ , "kfold"] = int(fold)

    train["kfold"] = train["kfold"].astype(int)
    print(train.head())
    
    
    ## Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(config.model)
    print("Tokenizer Downloaded")

    # Device
    if config.device == "mps":
        device = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
        
    elif config.device == "cuda":
        device = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")
        
    else:
        device = torch.device("cpu")

    print("Device", device)
    
    ### folds_run
    best_scores = []
    
    for fold in trange(0, config.n_folds, desc='Fold Loop'):
    # for fold in trange(0, config['n_folds']):
        print(f"{y_}==== Fold: {fold} ====={sr_}")

        # DataLoaders
        # collate_fn = DataCollatorWithPadding(tokenizer=config['tokenizer'] )
        train_loader, valid_loader = prepare_loader(train, fold, config.max_length, tokenizer, DataCollatorWithPadding(tokenizer=tokenizer))

        # Define Model because of KFold
        model = Model(config.model).to(config.device)

        # Loss Function
        loss_fn = nn.NLLLoss().to(config.device)
        print("Loss Function Defined")

        # Define Opimizer and Scheduler
        optimizer = AdamW(model.parameters(), lr = config.learning_rate, weight_decay = config.weight_decay)
        print("Optimizer Defined")
        
        # scheduler = fetch_scheduler(optimizer)
        scheduler = CosineWarmupScheduler(optimizer=optimizer, warmup=100, max_iters=2000)
        print("Scheduler Defined")
        
        print("자세히 알고 싶으면 코드를 봅시다.")
        ## Start Training
        model, best_score = run_train(model, config.model_save, train_loader, valid_loader, loss_fn, optimizer, device, n_classes, fold, scheduler, config["grad_clipping"], config["n_epochs"])
    
        ## Best F1_Score per Fold 줍줍
        if type(best_score) == torch.Tensor:
            best_scores.append( best_score.detach().cpu().item() )
        else:
            best_scores.append(best_score)
        
        ## For Memory
        del model, train_loader, valid_loader

        torch.cuda.empty_cache()
        _ = gc.collect()

    print(best_scores)
    print("Train Completed")

if __name__ == '__main__':
    config = define()
    main(config)

    
    
    
    
    

