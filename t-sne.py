import argparse
import os
import time
import torch
import torch.nn as nn
import torch.backends.cudnn as cudnn
import torch.optim
import torch.utils.data
import torchvision.transforms as transforms
import numpy as np
from models import API_Net
from datasets import RandomDataset_test
from utils import accuracy_test_open_set, AverageMeter
import sys
import pandas as pd
from sklearn.manifold import TSNE
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib
import tikzplotlib
from matplotlib.pyplot import figure
from tqdm import tqdm


# python -u t-sne_2d.py -b 1 --n_classes_total 4 --resume saved_models/res101/2568987/model_best.pth.tar
np.set_printoptions(suppress=True,
                    formatter={'float_kind': '{:0.4f}'.format})

parser = argparse.ArgumentParser(description='PyTorch ImageNet Training')
parser.add_argument('--exp_name', default=None, type=str,
                    help='name of experiment')
parser.add_argument('--data', metavar='DIR', default='',
                    help='path to dataset')
parser.add_argument('-j', '--workers', default=0, type=int, metavar='N',
                    help='number of data loading workers (default: 4)')
parser.add_argument('--epochs', default=100, type=int, metavar='N',
                    help='number of total epochs to run')
parser.add_argument('--start-epoch', default=0, type=int, metavar='N',
                    help='manual epoch number (useful on restarts)')
parser.add_argument('-b', '--batch-size', default=1, type=int,
                    metavar='N', help='mini-batch size (default: 256)')
parser.add_argument('--lr', '--learning-rate', default=0.01, type=float,
                    metavar='LR', help='initial learning rate')
parser.add_argument('--momentum', default=0.9, type=float, metavar='M',
                    help='momentum')
parser.add_argument('--weight-decay', '--wd', default=5e-4, type=float,
                    metavar='W', help='weight decay (default: 1e-4)')
parser.add_argument('--print-freq', '-p', default=100, type=int,
                    metavar='N', help='print frequency (default: 10)')
parser.add_argument('--evaluate-freq', default=10, type=int,
                    help='the evaluation frequence')
parser.add_argument('--resume', default='./checkpoint.pth.tar', type=str, metavar='PATH',
                    help='path to latest checkpoint (default: none)')
parser.add_argument('--model_load_path', default='./save', type=str,
                    help='model path you want to test')
parser.add_argument('--output_path', default='./output/test.txt', type=str,
                    help='test result output path')
parser.add_argument('-e', '--evaluate', dest='evaluate', action='store_true',
                    help='evaluate model on validation set')
parser.add_argument('--pretrained', dest='pretrained', action='store_true',
                    help='use pre-trained model')
parser.add_argument('--n_classes', default=2, type=int,
                    help='the number of classes')
parser.add_argument('--n_classes_total', default=5, type=int,
                    help='the overall number of classes')
parser.add_argument('--n_samples', default=8, type=int,
                    help='the number of samples per class')
parser.add_argument('--test_list', default='data_list/tsne_list_ff_test.txt', type=str,
                    help='test list')
parser.add_argument('--model_name', default='res101', type=str)
parser.add_argument('--dist_type', default='euclidean', type=str)
parser.add_argument('--image_loader', default='default_loader', type=str)


device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(device)

def main(args):
    test_list = args.test_list
    n_classes_total = args.n_classes_total
    model_name = args.model_name
    dist_type = args.dist_type
    image_loader = args.image_loader

    # create model
    model = API_Net(num_classes=n_classes_total, model_name=model_name)
    model = model.to(device)
    model.conv = nn.DataParallel(model.conv)

    if os.path.isfile(args.resume):
        print('loading checkpoint {}'.format(args.resume))
        checkpoint = torch.load(args.resume)
        model.load_state_dict(checkpoint['state_dict'])
        print('loaded checkpoint {}(epoch {})'.format(args.resume, checkpoint['epoch']))
    else:
        print('no checkpoint found at {}'.format(args.resume))

    test_dataset = RandomDataset_test(val_list=test_list,
                                      loader=image_loader,
                                      transform=transforms.Compose([
                                          transforms.Resize([512, 512]),
                                          transforms.CenterCrop([448, 448]),
                                          transforms.ToTensor(),
                                          transforms.Normalize(
                                              mean=(0.485, 0.456, 0.406),
                                              std=(0.229, 0.224, 0.225)
                                          )]))
    test_loader = torch.utils.data.DataLoader(
        test_dataset, batch_size=args.batch_size, shuffle=False,
        num_workers=args.workers, pin_memory=True)

    features, labels = test(test_loader, model, dist_type)  # shape: [449,1048]

    print(features.shape)
    print(labels.shape)

    tsne = TSNE(n_components=2, random_state=0, init='pca')
    projections = tsne.fit_transform(features)

    sne_plot = pd.DataFrame()
    sne_plot["comp-1"] = projections[:, 0]
    sne_plot["comp-2"] = projections[:, 1]

    figure(figsize=(10, 10), dpi=100)

    ax = sns.scatterplot(x="comp-1", y="comp-2", hue=labels.tolist(),
                         data=sne_plot, s=500, legend='full', style=labels.tolist(),
                         palette=sns.color_palette("husl", 5))

    ax.set_title("T-SNE projection", fontsize=50)
    plt.setp(ax.get_legend().get_texts(), fontsize='1500')
    ax.legend(markerscale=3)
    plt.xticks(fontsize=10)
    plt.yticks(fontsize=10)

    # plt.legend(labels=['original', 'DF', 'F2F', 'FS', 'NT', 'DFDC_Real', 'DFDC_fake', 'Celeb_real', 'Youtube_real',
    #                    'Celeb-synthesis', 'Deeper_Fake', 'Deeper_Real', 'Faceshifter', 'DeepFakeDetection'])
    # tikzplotlib.save('plots/2568987_ff.tex')
    plt.savefig('plots/3367609.png')
    # plt.show()


def test(test_loader, model, dist_type):

    # switch to evaluate mode
    model.eval()
    features = pd.DataFrame()
    labels = pd.Series(dtype=int)

    with torch.no_grad():
        for i, (input, target, image_name) in enumerate(tqdm(test_loader)):
            input_val = input.to(device)
            # target_val = target.to(device)

            # compute output
            feature = model(input_val, targets=None, flag='tsne', dist_type=dist_type)
            feature = feature.cpu()
            feature = feature.view(1, -1)
            df_f = pd.DataFrame(feature)
            features = pd.concat([features, df_f], ignore_index=True)

            df_l = pd.Series(target.view(-1))
            labels = pd.concat([labels, df_l], ignore_index=True)

    return features, labels


if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
