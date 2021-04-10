# -*- coding: utf-8 -*-
"""Copy of Copy of APS360_Model_Training.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1-D8Oe_wKJSoc1jQQV16R_J_jqcJIvbWR

# Data Cleaning/Embedding
"""

import pandas as pd
import torchtext
import torch
import torch.nn as nn
import numpy as np
import matplotlib.pyplot as plt
import spacy

embed_dim = 50
# The first time you run this will download a ~823MB file
glove = torchtext.vocab.GloVe(name="6B", # trained on Wikipedia 2014 corpus
                              dim=embed_dim)   # embedding size = 100

import os
from getpass import getpass
import urllib
# user = input('User name: ')
# password = getpass('Password: ')
# password = urllib.parse.quote(password) # your password is converted into url format
branch="main"

# cmd_string = 'git clone https://{0}:{1}@github.com/gmin7/audio_sr'.format(user, password)
cmd_string = 'git clone https://github.com/yuyang-wen/AI-Project.git'
os.system(cmd_string)

!unzip /content/AI-Project/test_set.csv.zip
!unzip /content/AI-Project/train_set.csv.zip
!unzip /content/AI-Project/val_set.csv.zip

# define the columns that we want to process and how to process
# use default tokenizer (string.split())
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

text_field = torchtext.legacy.data.Field(sequential=True, 
                                         include_lengths=True, 
                                         use_vocab=True,
                                         batch_first=True)

label_field = torchtext.legacy.data.Field(sequential=False, 
                                          use_vocab=False, 
                                          pad_token=None, 
                                          unk_token=None,
                                          batch_first=True,
                                          preprocessing=lambda x: int(x == 'D'))

fields = [
    ('tweet', text_field), # process it as text
    ('id', None), # we dont need this, so no processing
    ('conversation_id', None), # we dont need this, so no processing
    ('party', label_field) # process it as label
]

trainds, valds, testds = torchtext.legacy.data.TabularDataset.splits(path='', 
                                                                    format='csv', 
                                                                    train='train_set.csv', 
                                                                    validation='val_set.csv',
                                                                    test='test_set.csv', 
                                                                    fields=fields, 
                                                                    skip_header=True)

# Build vocab
text_field.build_vocab(trainds,vectors=glove)

def get_data_loader(batch_size):
  traindl = torchtext.legacy.data.BucketIterator(trainds, # specify train and validation Tabulardataset
                                                batch_size=batch_size,  # batch size of train and validation
                                                sort_key=lambda x: len(x.tweet), # on what attribute the text should be sorted
                                                sort_within_batch=True, 
                                                repeat=False,
                                                 device=device)
  
  valdl = torchtext.legacy.data.BucketIterator(valds, # specify train and validation Tabulardataset
                                              batch_size=batch_size,  # batch size of train and validation
                                              sort_key=lambda x: len(x.tweet), # on what attribute the text should be sorted
                                              sort_within_batch=True, 
                                              repeat=False,
                                               device=device)
    
  testdl = torchtext.legacy.data.BucketIterator(testds, # specify train and validation Tabulardataset
                                                batch_size=batch_size,  # batch size of train and validation
                                                sort_key=lambda x: len(x.tweet), # on what attribute the text should be sorted
                                                sort_within_batch=True, 
                                                repeat=False,
                                                device=device)

  return traindl, valdl, testdl

"""# Model"""

# Example taken from lab

class TweetRNN(nn.Module):
    def __init__(self, input_size, hidden_size):
        super(TweetRNN, self).__init__()
        # not trainable for now
        self.emb = nn.Embedding.from_pretrained(text_field.vocab.vectors.cuda()).cuda()
        self.hidden_size = hidden_size
        self.rnn = nn.RNN(input_size, hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, 2)
    
    def forward(self, x):
        # Look up the embedding
        x = self.emb(x)
        # Set an initial hidden state
        h0 = torch.zeros(1, x.size(0), self.hidden_size).cuda()
        # Forward propagate the RNN
        out, _ = self.rnn(x, h0)
        # Pass the output of the last time step to the classifier
        out = self.fc(out[:, -1, :])
        return out

# CNN-RNN dual architecture

class CNN_RNN(nn.Module):
    def __init__(self, input_size, hidden_size, nb_filters):
        super(CNN_RNN, self).__init__()
        # not trainable for now
        self.emb = nn.Embedding.from_pretrained(text_field.vocab.vectors.cuda(),freeze=False).cuda()
        self.hidden_size = hidden_size
        self.nb_filters = nb_filters
        self.cnn1  = nn.Conv1d(embed_dim, nb_filters, 4,padding=2) # filters are 200 in original paper (input_dim, numer of filters, filter len)
        self.cnn2  = nn.Conv1d(embed_dim, nb_filters, 5,padding=2)
        self.max1 = nn.MaxPool1d(2,ceil_mode=True)
        self.gru = nn.GRU(nb_filters, hidden_size, batch_first=True)
        self.fc1 = nn.Linear(hidden_size, nb_filters*2)
        self.fc2 = nn.Linear(nb_filters*2, 2)

    
    def forward(self, x):
        # Look up the embedding
        x = self.emb(x)
        input = x.transpose(2,1) # CNN requires input of shape (B,Cin,L)
        # Now apply CNN with filter len 4
        x = self.cnn1(input)
        # Apply pooling to halve the len
        x = self.max1(x)
        y = self.cnn2(input)
        y= self.max1(y)
        x = torch.cat((x,y),2)
        # RNN input (SL,B,IN)
        x = x.permute(2,0,1)
        # Set an initial hidden state
        h0 = torch.zeros(1, x.size(0), self.hidden_size).cuda()
        # Forward propagate the RNN
        out, _ = self.gru(x, h0)
        # Pass the output of the last time step to the classifier
        out = self.fc1(out[-1, :, :])
        out = self.fc2(out)
        return out

"""# Training"""

def train_network(model, train_loader, valid_loader, num_epochs=5, learning_rate=1e-5, plot=False):
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    train_losses, valid_losses, train_acc, valid_acc = [], [], [], []
    epochs = []
    for epoch in range(num_epochs):
        for batch in train_loader:
            optimizer.zero_grad()
            data = batch.tweet[0].cuda()
            labels = batch.party.cuda()
            pred = model(data)
            train_loss = criterion(pred, labels)
            train_loss.backward()
            optimizer.step()

        for batch in valid_loader:
            optimizer.zero_grad()
            pred = model(batch.tweet[0])
            valid_loss = criterion(pred, batch.party)
            
        train_losses.append(float(train_loss))
        valid_losses.append(float(valid_loss))     
        epochs.append(epoch)
        train_acc.append(get_accuracy(model, train_loader))
        valid_acc.append(get_accuracy(model, valid_loader))
        print("Epoch %d; Train Loss %f; Val Loss %f; Train Acc %f; Val Acc %f" % (
            epoch+1, train_loss, valid_loss, train_acc[-1], valid_acc[-1]))

        # TODO: Save model
    

    # plotting
    if plot:
      plt.title("Accuracy Curve")
      plt.plot(epochs, train_acc, label="Train")
      plt.plot(epochs, valid_acc, label="Validation")
      plt.xlabel("Epoch")
      plt.ylabel("Accuracy")
      plt.legend(loc='best')
      plt.show()

      plt.title("Loss Curve")
      plt.plot(epochs, train_losses, label="Train")
      plt.plot(epochs, valid_losses, label="Validation")
      plt.xlabel("Epoch")
      plt.ylabel("Loss")
      plt.legend(loc='best')
      plt.show()

    print("Final Training Accuracy: {}".format(train_acc[-1]))
    print("Final Validation Accuracy: {}".format(valid_acc[-1]))

def get_accuracy(model, data):
    correct, total = 0, 0
    for batch in data:
        output = model(batch.tweet[0])
        pred = output.max(1, keepdim=True)[1]
        correct += pred.eq(batch.party.view_as(pred)).sum().item()
        total += batch.party.shape[0]
    return correct / total

# input_size = len(text_field.vocab.itos)
# print(input_size)

# model = TweetRNN(50, 100)
# train_loader,valid_loader,test_loader = get_data_loader(256)
# model = model.cuda()

# train_network(model, train_loader, valid_loader, num_epochs=50, plot=True)

"""# CNN_RNN Model"""

# input_size = len(text_field.vocab.itos)
# print(input_size)

model = CNN_RNN(50, 100, 100)
train_loader,valid_loader,test_loader = get_data_loader(64)
model = model.cuda()
train_network(model, train_loader, valid_loader, num_epochs=50, plot=True,learning_rate=1e-03)

# for batch in train_loader:
#   print(batch.tweet[0])
#   break

# torch.save(model,"saved_model")

# from google.colab import files
# files.download('saved_model')