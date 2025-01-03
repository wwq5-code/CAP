import sys

sys.argv = ['']
del sys

import os
# os.environ['CUDA_LAUNCH_BLOCKING'] = "1"


import math

import argparse
from torch.autograd import Variable
import torch
import torch.nn as nn
import torch.optim
import torchvision
from torchvision.datasets import MNIST, CIFAR10, FashionMNIST, CIFAR100, CelebA
from torch.utils.data import DataLoader, TensorDataset, random_split, ConcatDataset
import torch.utils.data as Data
import torch.nn.functional as F
import torchvision.transforms as T
from torchvision import datasets, transforms
import matplotlib.pyplot as plt
import numpy as np
from torch.utils.data import DataLoader, Dataset, Subset
import copy
import random
import time
from torch.nn.functional import cosine_similarity

class My_subset(Dataset):
    r"""
    Subset of a dataset at specified indices.

    Arguments:
        dataset (Dataset): The whole Dataset
        indices (sequence): Indices in the whole set selected for subset
        labels(sequence) : targets as required for the indices. will be the same length as indices
    """

    def __init__(self, dataset, indices):
        self.dataset = dataset
        self.indices = indices
        self.data, self.targets = self.get_image_label()

    def __getitem__(self, idx):
        image, label = self.dataset[self.indices[idx]]
        return (image, label)

    def __len__(self):
        return len(self.indices)

    def get_image_label(self, ):
        if args.dataset == "MNIST":
            temp_img = torch.empty(0, 1, 28, 28).float().to(args.device)
            temp_label = torch.empty(0).long().to(args.device)
            for id in self.indices:
                image, label = self.dataset[id]
                image, label = image.reshape(1, 1, 28, 28).to(args.device), torch.tensor([label]).long().to(args.device)
                # print(image)
                # print(label)
                # label = torch.tensor([label])
                temp_img = torch.cat([temp_img, image], dim=0)
                temp_label = torch.cat([temp_label, label], dim=0)
        elif args.dataset == "CIFAR10":
            temp_img = torch.empty(0, 3, 32, 32).float().to(args.device)
            temp_label = torch.empty(0).long().to(args.device)
            for id in self.indices:
                image, label = self.dataset[id]
                image, label = image.to(args.device).reshape(1, 3, 32, 32), torch.tensor([label]).long().to(args.device)
                # print(label)
                # label = torch.tensor([label])
                temp_img = torch.cat([temp_img, image], dim=0)
                temp_label = torch.cat([temp_label, label], dim=0)
        elif args.dataset == "CIFAR100":
            temp_img = torch.empty(0, 3, 32, 32).float().to(args.device)
            temp_label = torch.empty(0).long().to(args.device)
            for id in self.indices:
                image, label = self.dataset[id]
                image, label = image.to(args.device).reshape(1, 3, 32, 32), torch.tensor([label]).long().to(args.device)
                # print(label)
                # label = torch.tensor([label])
                temp_img = torch.cat([temp_img, image], dim=0)
                temp_label = torch.cat([temp_label, label], dim=0)

        print(temp_label.shape, temp_img.shape)
        d = Data.TensorDataset(temp_img, temp_label)
        return temp_img, temp_label


class Mine1(nn.Module):

    def __init__(self, noise_size=49, sample_size=28*28, output_size=1, hidden_size=128):
        super(Mine1, self).__init__()
        self.fc1_noise = nn.Linear(noise_size, hidden_size, bias=False)
        self.fc1_sample = nn.Linear(sample_size, hidden_size, bias=False)
        self.fc1_bias = nn.Parameter(torch.zeros(hidden_size))
        self.fc2 = nn.Linear(hidden_size, hidden_size)
        self.fc3 = nn.Linear(hidden_size, output_size)

        self.ma_et = None

        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.kaiming_normal_(m.weight)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0.0)

    def forward(self, noise, sample):
        x_noise = self.fc1_noise(noise)
        x_sample = self.fc1_sample(sample)
        x = F.leaky_relu(x_noise + x_sample + self.fc1_bias, negative_slope=2e-1)
        x = F.leaky_relu(self.fc2(x), negative_slope=2e-1)
        x = F.leaky_relu(self.fc3(x), negative_slope=2e-1)
        return x



# Function to mask 75% of the pixels
def apply_random_mask(images, mask_percent=0.75):
    B, C, H, W = images.shape

    # Calculate the total number of pixels to mask
    total_pixels = H * W
    mask_size = int(total_pixels * mask_percent)

    masked_images = images.clone()  # Clone the original images to keep them unchanged
    inverse_mask_list = torch.empty_like(images).cuda()
    for i in range(B):
        # Create a flattened mask with random 1s and 0s
        mask_flat = torch.ones(total_pixels).cuda()
        mask_flat[:mask_size] = 0
        mask_flat = mask_flat[torch.randperm(total_pixels)]

        # Reshape the mask and apply it to the image
        mask = mask_flat.view(H, W).unsqueeze(0).repeat(C, 1, 1)  # Repeat the mask for each channel
        masked_images[i] = images[i] * mask
        inverse_mask = 1 - mask
        inverse_mask_list[i] = images[i] * inverse_mask
#         print(masked_images)

    return masked_images, inverse_mask_list

def scoring_function(matrix):
    # This is a simple scoring function that returns the matrix itself as scores.
    # You can replace it with your own scoring function if needed.
    return matrix


def dp_sampling(matrix, epsilon, sample_size, replacement):
    scores = scoring_function(matrix)
    sensitivity = 1.0  # The sensitivity of our scoring function is 1

    # Calculate probabilities using the exponential mechanism
    probabilities = np.exp(epsilon * scores / (2 * sensitivity))
    probabilities /= probabilities.sum()

    # Flatten the matrix and probabilities for sampling
    flat_matrix = matrix.flatten()
    flat_probabilities = probabilities.flatten()

    # Sample elements without replacement
    sampled_indices = np.random.choice(
        np.arange(len(flat_matrix)),
        size=sample_size,
        replace=replacement,
        p=flat_probabilities
    )
    # Create the output matrix with 0s
    output_matrix = np.zeros_like(matrix)

    # Set the sampled elements to their original values
    np.put(output_matrix, sampled_indices, flat_matrix[sampled_indices])

    return output_matrix


class PoisonedDataset(Dataset):

    def __init__(self, dataset, base_label, trigger_label, poison_samples, mode="train", device=torch.device("cuda"),
                 dataname="MNIST", args=None, add_backdoor=1, dp_sample=0):
        # self.class_num = len(dataset.classes)
        # self.classes = dataset.classes
        # self.class_to_idx = dataset.class_to_idx
        self.device = device
        self.dataname = dataname
        self.ori_dataset = dataset
        self.add_backdoor = add_backdoor
        self.dp_sample = dp_sample
        self.args = args
        self.data, self.targets = self.add_trigger(self.reshape(dataset, dataname), dataset.targets, base_label,
                                                   trigger_label, poison_samples, mode)
        self.channels, self.width, self.height = self.__shape_info__()
        # self.data_test, self.targets_test = self.add_trigger_test(self.reshape(dataset.data, dataname), dataset.targets, base_label, trigger_label, portion, mode)

    def __getitem__(self, item):
        img = self.data[item]
        label_idx = self.targets[item]

        label = np.zeros(10)
        label[label_idx] = 1  # 把num型的label变成10维列表。
        label = torch.Tensor(label)

        img = img.to(self.device)
        label = label.to(self.device)

        return img, label

    def __len__(self):
        return len(self.data)

    def __shape_info__(self):
        return self.data.shape[1:]

    def reshape(self, dataset, dataname="MNIST"):
        if dataname == "MNIST":
            temp_img = dataset.data.reshape(len(dataset.data), 1, 28, 28).float()
        elif dataname == "CIFAR10":
            temp_img = torch.empty(0, 3, 32, 32).float().cuda()
            temp_label = torch.empty(0).long().cuda()
            for id in range(len(dataset)):
                image, label = dataset[id]
                image, label = image.cuda().reshape(1, 3, 32, 32), torch.tensor([label]).long().cuda()
                # print(label)
                # label = torch.tensor([label])
                temp_img = torch.cat([temp_img, image], dim=0)
                temp_label = torch.cat([temp_label, label], dim=0)
                # print(id)

        return np.array(temp_img.to("cpu"))

    def norm(self, data):
        offset = np.mean(data, 0)
        scale = np.std(data, 0).clip(min=1)
        return (data - offset) / scale

    def add_trigger(self, data, targets, base_label, trigger_label, poison_samples, mode):
        print("## generate——test " + mode + " Bad Imgs")
        new_data = copy.deepcopy(data)
        new_targets = []
        new_data_re = []

        # total_poison_num = int(len(new_data) * portion/10)
        _, width, height = data.shape[1:]
        for i in range(len(data)):
            if targets[i] == base_label:
                new_targets.append(trigger_label)
                if trigger_label != base_label:
                    if self.add_backdoor == 1:
                        new_data[i, :, width - 3, height - 3] = 255
                        new_data[i, :, width - 3, height - 4] = 255
                        new_data[i, :, width - 4, height - 3] = 255
                        new_data[i, :, width - 4, height - 4] = 255
                    # new_data[i, :, width - 23, height - 21] = 254
                    # new_data[i, :, width - 23, height - 22] = 254
                # new_data[i, :, width - 22, height - 21] = 254
                # new_data[i, :, width - 24, height - 21] = 254
                new_data[i] = new_data[i] / 255

                if self.dp_sample == 1:
                    replacement = False
                    sampled_matrix = dp_sampling(new_data[i], args.epsilon, args.dp_sampling_size, replacement)
                    new_data_re.append(sampled_matrix)
                elif self.dp_sample == 2:
                    replacement = True
                    sampled_matrix = dp_sampling(new_data[i], args.epsilon, args.dp_sampling_size, replacement)
                    new_data_re.append(sampled_matrix)
                else:
                    new_data_re.append(new_data[i])
                # print("new_data[i]",new_data[i])
                poison_samples = poison_samples - 1
                if poison_samples <= 0:
                    break
                # x=torch.tensor(new_data[i])
                # x_cpu = x.cpu().data
                # x_cpu = x_cpu.clamp(0, 1)
                # x_cpu = x_cpu.view(1, 1, 28, 28)
                # grid = torchvision.utils.make_grid(x_cpu, nrow=1 )
                # plt.imshow(np.transpose(grid, (1, 2, 0)))  # 交换维度，从GBR换成RGB
                # plt.show()

        return torch.Tensor(new_data_re), torch.Tensor(new_targets).long()


class SimpleCNN(torch.nn.Module):
    def __init__(self):
        super(SimpleCNN, self).__init__()
        self.conv1 = torch.nn.Conv2d(1, 1, kernel_size=3, stride=1, padding=1)

    def forward(self, x):
        x = self.conv1(x)
        return x


def data_reshape_to_np(dataset, dataname="MNIST"):
    if dataname == "MNIST":
        temp_img = dataset.data.reshape(len(dataset.data), 1, 28, 28).float()
    elif dataname == "CIFAR10":
        temp_img = torch.empty(0, 3, 32, 32).float().cuda()
        temp_label = torch.empty(0).long().cuda()
        for id in range(len(dataset)):
            image, label = dataset[id]
            image, label = image.cuda().reshape(1, 3, 32, 32), torch.tensor([label]).long().cuda()
            # print(label)
            # label = torch.tensor([label])
            temp_img = torch.cat([temp_img, image], dim=0)
            temp_label = torch.cat([temp_label, label], dim=0)
            # print(id)

    return np.array(temp_img.to("cpu"))




def generate_gray_noise(image):
    # Add Gaussian noise
    mean = 0.0  # mean of the Gaussian noise
    stddev = 0.8  # standard deviation of the Gaussian noise
    noise = torch.normal(mean, stddev, size=image.shape).cuda()
    noisy_image = image + noise

    # Clip the values to be between 0 and 1
    noisy_image = torch.clamp(noisy_image, 0, 1)
    gray_image = noisy_image.mean(dim=0, keepdim=True)

    ###############################################
    # now image is the original image, gray_image is the image that we generated using noise

    # Scale to [0, 255] and convert to integers
    image_int = (image * 255).int()
    gray_image_int = (gray_image * 255).int()

    # Clear the least significant bit of the red channel in the original image
    image_int[0, :, :] = image_int[0, :, :] & 0b11100000

    # Scale the grayscale image to use the least significant bit only
    gray_image_lsb = gray_image_int.squeeze() >> 3

    # Embed the grayscale image into the least significant bit of the red channel
    image_steg = image_int.clone()
    image_steg[0, :, :] = image_steg[0, :, :] | gray_image_lsb

    # Convert back to float in [0, 1] range
    image_steg = image_steg.float() / 255.0

    return image_steg


def add_laplace_noise(image, args):
    # Parameters for Laplace noise

    loc = torch.tensor([0.0], device='cuda')  # mean (location parameter) of the Laplace distribution
    scale = torch.tensor([args.laplace_scale], device='cuda')  # diversity (scale) parameter for Laplace distribution
    laplace = torch.distributions.laplace.Laplace(loc, scale)

    # Generate Laplace noise
    laplace_noise = laplace.sample(image.shape)
    laplace_noise = laplace_noise.squeeze(-1)

    noisy_image = image + laplace_noise.cpu()

    # Clip the values to be between 0 and 1
    noisy_image = torch.clamp(noisy_image, 0, 1)

    return noisy_image


def generate_gray_laplace_small_trigger_noise(image):
    # Parameters for Laplace noise
    loc = torch.tensor([0.5], device='cuda')  # mean (location parameter) of the Laplace distribution
    scale = torch.tensor([0.5], device='cuda')  # diversity (scale) parameter for Laplace distribution

    # in a dp explanation, the scale = delta_f / epsilon

    # Initialize Laplace distribution
    laplace = torch.distributions.laplace.Laplace(loc, scale)

    # Generate Laplace noise
    laplace_noise = laplace.sample(image.shape)
    laplace_noise = laplace_noise.squeeze(-1)

    noisy_image = image + laplace_noise.cpu()

    # print(laplace_noise.shape, image.shape)

    # Clip the values to be between 0 and 1
    noisy_image = torch.clamp(noisy_image, 0, 1)
    gray_image = noisy_image.mean(dim=0, keepdim=True)

    ###############################################
    # now image is the original image, gray_image is the image that we generated using noise

    # Scale to [0, 255] and convert to integers
    image_int = (image * 255).int()
    gray_image_int = (gray_image * 255).int()

    # here we change the noised image to the small (2, 2) image
    # Downsample feature_map to 4x4 using adaptive average pooling
    feature_map_downsampled = torch.nn.functional.adaptive_avg_pool2d(gray_image, (2, 2))

    # print(feature_map_downsampled.shape)
    gray_image_down_sampled_int = (feature_map_downsampled * 255).int()

    # Clear the least significant bit of the red channel in the original image
    image_int[0, -4:-2, -4:-2] = image_int[0, -4:-2, -4:-2] & 0b00000000

    # Scale the grayscale image to use the least significant bit only
    gray_image_lsb = gray_image_down_sampled_int.squeeze() >> 0

    # Embed the grayscale image into the least significant bit of the red channel
    image_steg = image_int.clone()
    image_steg[0, -4:-2, -4:-2] = image_steg[0, -4:-2, -4:-2] | gray_image_lsb
    # original
    # image_steg[0, :, :] = image_steg[0, :, :] | gray_image_lsb

    # Convert back to float in [0, 1] range
    image_steg = image_steg.float() / 255.0

    return image_steg


def generate_gray_laplace_noise_with_steganography(image):
    # Parameters for Laplace noise
    loc = torch.tensor([0.0], device='cuda')  # mean (location parameter) of the Laplace distribution
    scale = torch.tensor([0.5], device='cuda')  # diversity (scale) parameter for Laplace distribution

    # in a dp explanation, the scale = delta_f / epsilon

    # Initialize Laplace distribution
    laplace = torch.distributions.laplace.Laplace(loc, scale)

    # Generate Laplace noise
    laplace_noise = laplace.sample(image.shape)
    laplace_noise = laplace_noise.squeeze(-1)

    noisy_image = image + laplace_noise.cpu()

    # print(laplace_noise.shape, image.shape)

    # Clip the values to be between 0 and 1
    noisy_image = torch.clamp(noisy_image, 0, 1)
    gray_image = noisy_image.mean(dim=0, keepdim=True)

    ###############################################
    # now image is the original image, gray_image is the image that we generated using noise

    # Scale to [0, 255] and convert to integers
    image_int = (image * 255).int()
    gray_image_int = (gray_image * 255).int()

    # here we change the noised image to the small (2, 2) image
    # Downsample feature_map to 4x4 using adaptive average pooling
    feature_map_downsampled = torch.nn.functional.adaptive_avg_pool2d(gray_image, (2, 2))

    # print(feature_map_downsampled.shape)
    gray_image_down_sampled_int = (feature_map_downsampled * 255).int()

    # Clear the least significant bit of the red channel in the original image
    image_int[0, :, :] = image_int[0, :, :] & 0b11100000

    # Scale the grayscale image to use the least significant bit only
    gray_image_lsb = gray_image_int.squeeze() >> 3

#     print(gray_image_lsb)
    # Embed the grayscale image into the least significant bit of the red channel
    image_steg = image_int.clone()
    image_steg[0, :, :] = image_steg[0, :, :] | gray_image_lsb
    # original
    # image_steg[0, :, :] = image_steg[0, :, :] | gray_image_lsb

    # Convert back to float in [0, 1] range
    image_steg = image_steg.float() / 255.0

    return image_steg


def generate_gray_laplace_noise(image):
    # Parameters for Laplace noise
    loc = torch.tensor([0.3], device='cuda')  # mean (location parameter) of the Laplace distribution
    scale = torch.tensor([0.8], device='cuda')  # diversity (scale) parameter for Laplace distribution

    # in a dp explanation, the scale = delta_f / epsilon

    # Initialize Laplace distribution
    laplace = torch.distributions.laplace.Laplace(loc, scale)

    # Generate Laplace noise
    laplace_noise = laplace.sample(image.shape)
    laplace_noise = laplace_noise.squeeze(-1)

    noisy_image = image + laplace_noise

    # Clip the values to be between 0 and 1
    noisy_image = torch.clamp(noisy_image, 0, 1)
    gray_image = noisy_image.mean(dim=0, keepdim=True)

    ###############################################
    # now image is the original image, gray_image is the image that we generated using noise

    # Scale to [0, 255] and convert to integers
    image_int = (image * 255).int()
    gray_image_int = (gray_image * 255).int()

    # Clear the least significant bit of the red channel in the original image
    image_int[0, :, :] = image_int[0, :, :] & 0b11100000

    # Scale the grayscale image to use the least significant bit only
    gray_image_lsb = gray_image_int.squeeze() >> 3

    # Embed the grayscale image into the least significant bit of the red channel
    image_steg = image_int.clone()
    image_steg[0, :, :] = image_steg[0, :, :] | gray_image_lsb

    # Convert back to float in [0, 1] range
    image_steg = image_steg.float() / 255.0

    return image_steg


def add_trigger(add_backdoor, data, targets, poison_samples, mode, feature_extra):
    print("## generate——test " + mode + " Bad Imgs")
    new_data = copy.deepcopy(data)
    new_data_re = []
    print(new_data.shape)

    # total_poison_num = int(len(new_data) * portion/10)
    _, width, height = data.shape[1:]
    for i in range(len(data)):
        if add_backdoor == 1:

            image_steg = generate_gray_laplace_small_trigger_noise(new_data[i])
            new_data[i] = image_steg
            # Plotting
            # plt.imshow(embedded_image)
            # plt.title("Image with Embedded Feature Map")
            # plt.axis('off')
            # plt.show()

            # new_data[i, :, width - 3, height - 3] = 1
            # new_data[i, :, width - 3, height - 4] = 1
            # new_data[i, :, width - 4, height - 3] = 1
            # new_data[i, :, width - 4, height - 4] = 1

            # new_data[i, :, width - 23, height - 21] = 254
            # new_data[i, :, width - 23, height - 22] = 254
            # new_data[i, :, width - 22, height - 21] = 254
            # new_data[i, :, width - 24, height - 21] = 254
            # new_data[i] = torch.from_numpy(embedded_image).view([1,28,28])
            #      new_data_re.append(embedded_image)
            poison_samples = poison_samples - 1
            if poison_samples <= 0:
                break
        # x=torch.tensor(new_data[i])
        # x_cpu = x.cpu().data
        # x_cpu = x_cpu.clamp(0, 1)
        # x_cpu = x_cpu.view(1, 1, 28, 28)
        # grid = torchvision.utils.make_grid(x_cpu, nrow=1 )
        # plt.imshow(np.transpose(grid, (1, 2, 0)))  # 交换维度，从GBR换成RGB
        # plt.show()

    # print(len(new_data_re))
    return data, targets  # new_data


def prepare_verification_dataset( er_clean_on_re_set, er_on_rem_with_tri_set, er_clean_set, er_with_trigger_set, remaining_grad_set, args):

    erased_set_with_tri_list = list(er_with_trigger_set)
    erased_on_rem_with_tri_list = list(er_on_rem_with_tri_set)
    er_clean_set_list = list(er_clean_set)

    combined_not_in_set = erased_set_with_tri_list + erased_on_rem_with_tri_list + er_clean_set_list

    er_clean_on_re_set_list = list(er_clean_on_re_set)
    remaining_set_list = list(remaining_grad_set)

    combined_in_set = er_clean_on_re_set_list + remaining_set_list



    for i in range(len(combined_not_in_set)):
        grad, img = combined_not_in_set[i]
        combined_not_in_set[i] = grad, img, 0

    for i in range(len(combined_in_set)):
        grad, img = combined_in_set[i]

        combined_in_set[i] = grad, img, 1

    indices_not_in = list(range(len(combined_not_in_set)))
    indices_in = list(range(len(combined_in_set)))

    subset_no = Subset(combined_not_in_set, indices_not_in)
    subset_with = Subset(combined_in_set, indices_in)

    constructed_no_with = ConcatDataset([subset_no, subset_with])

    return constructed_no_with


def add_trigger_new(add_backdoor, dataset, poison_samples, mode, args):
    print("## generate——test " + mode + " Bad Imgs")

    # indices = dataset.indices
    list_from_dataset_tuple = list(dataset)
    indices = list(range(len(list_from_dataset_tuple)))
    new_data_re = []

    x, y = list_from_dataset_tuple[0]
    total_cosine_simi = 0
    count_idx = 0
    # total_poison_num = int(len(new_data) * portion/10)
    _, width, height = x.shape

    for i in range(len(list_from_dataset_tuple)):
        if add_backdoor == 1:

            x, y = list_from_dataset_tuple[i]
            # x = add_laplace_noise(x, args) #generate_gray_laplace_small_trigger_noise(x)
            # new_data[i] = image_steg

            # Plotting
            # plt.imshow(embedded_image)
            # plt.title("Image with Embedded Feature Map")
            # plt.axis('off')
            # plt.show()
            img = x * 255
            temp = 1 - x[:, -7:-2, -7:-2]
            x[:, -7:-2, -7:-2] = x[:, -7:-2, -7:-2] + temp * args.laplace_scale

            img2 = x * 255
            cos_sim = cosine_similarity(img2.view(1,-1), img.view(1,-1))
            total_cosine_simi += cos_sim.mean().item()
            count_idx += 1
            # add trigger as general backdoor
            # x[:, width - 3, height - 3] = args.laplace_scale
            # x[:, width - 3, height - 4] = args.laplace_scale
            # x[:, width - 4, height - 3] = args.laplace_scale
            # x[:, width - 4, height - 4] = args.laplace_scale

            list_from_dataset_tuple[i] = x, y
            # new_data[i, :, width - 23, height - 21] = 254
            # new_data[i, :, width - 23, height - 22] = 254
            # new_data[i, :, width - 22, height - 21] = 254
            # new_data[i, :, width - 24, height - 21] = 254
            # new_data[i] = torch.from_numpy(embedded_image).view([1,28,28])
            #      new_data_re.append(embedded_image)
            poison_samples = poison_samples - 1
            if poison_samples <= 0:
                break
        # x=torch.tensor(new_data[i])
        # x_cpu = x.cpu().data
        # x_cpu = x_cpu.clamp(0, 1)
        # x_cpu = x_cpu.view(1, 1, 28, 28)
        # grid = torchvision.utils.make_grid(x_cpu, nrow=1 )
        # plt.imshow(np.transpose(grid, (1, 2, 0)))  # 交换维度，从GBR换成RGB
        # plt.show()

    # print(len(new_data_re))
    print("avg similarity", total_cosine_simi/count_idx)
    return Subset(list_from_dataset_tuple, indices)


def args_parser():
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--dataset', choices=['MNIST', 'CIFAR10'], default='MNIST')
    parser.add_argument('--cuda', action='store_true')
    parser.add_argument('--num_epochs', type=int, default=10, help='Number of training epochs for VIBI.')
    parser.add_argument('--explainer_type', choices=['Unet', 'ResNet_2x', 'ResNet_4x', 'ResNet_8x'],
                        default='ResNet_4x')
    parser.add_argument('--xpl_channels', type=int, choices=[1, 3], default=1)
    parser.add_argument('--k', type=int, default=12, help='Number of chunks.')
    parser.add_argument('--beta', type=float, default=0, help='beta in objective J = I(y,t) - beta * I(x,t).')
    parser.add_argument('--unlearning_ratio', type=float, default=0.1)
    parser.add_argument('--num_samples', type=int, default=4,
                        help='Number of samples used for estimating expectation over p(t|x).')
    parser.add_argument('--resume_training', action='store_true')
    parser.add_argument('--save_best', action='store_true',
                        help='Save only the best models (measured in valid accuracy).')
    parser.add_argument('--save_images_every_epoch', action='store_true', help='Save explanation images every epoch.')
    parser.add_argument('--jump_start', action='store_true', default=False)
    args = parser.parse_args()
    return args


class LinearModel(nn.Module):
    # 定义神经网络
    def __init__(self, n_feature=192, h_dim=3 * 30, n_output=10):
        # 初始化数组，参数分别是初始化信息，特征数，隐藏单元数，输出单元数
        super(LinearModel, self).__init__()
        self.fc1 = nn.Linear(n_feature, h_dim)  # 第一个全连接层
        self.fc2 = nn.Linear(h_dim, n_output)  # output

    # 设置隐藏层到输出层的函数

    def forward(self, x):
        # 定义向前传播函数
        x = F.relu(self.fc1(x))
        return self.fc2(x)

class Decoder(nn.Module):
    def __init__(self):
        super(Decoder, self).__init__()
        # Start with a linear layer to get the correct number of features
        self.fc = nn.Linear(128, 512)

        # Upscale to the desired dimensions using transposed convolutions
        self.deconv1 = nn.ConvTranspose2d(512, 256, kernel_size=4, stride=2, padding=1) # Output: 256 x 2 x 2
        self.deconv2 = nn.ConvTranspose2d(256, 128, kernel_size=4, stride=2, padding=1) # Output: 128 x 4 x 4
        self.deconv3 = nn.ConvTranspose2d(128, 64, kernel_size=4, stride=2, padding=1)  # Output: 64 x 8 x 8
        self.deconv4 = nn.ConvTranspose2d(64, 32, kernel_size=4, stride=2, padding=1)  # Output: 32 x 16 x 16

        # Final layer to produce an output of 3 channels (CIFAR-10 image)
        self.deconv5 = nn.ConvTranspose2d(32, 3, kernel_size=4, stride=2, padding=1)  # Output: 3 x 32 x 32

        # Activation functions
        self.relu = nn.ReLU()
        self.sigmoid = nn.Sigmoid()  # Sigmoid for final layer to output values in [0, 1]

    def forward(self, x):
        x = self.relu(self.fc(x))
        x = x.view(-1, 512, 1, 1)  # Reshape to start the transposed convolutions
        x = self.relu(self.deconv1(x))
        x = self.relu(self.deconv2(x))
        x = self.relu(self.deconv3(x))
        x = self.relu(self.deconv4(x))
        x = self.sigmoid(self.deconv5(x))  # Use sigmoid if the image values are normalized between 0 and 1
        return x



def conv_block(in_channels, out_channels, stride=1):
    return nn.Sequential(
        nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=stride, padding=1, bias=False),
        nn.BatchNorm2d(out_channels),
        nn.ReLU(inplace=True),
        nn.Conv2d(out_channels, out_channels, kernel_size=1, stride=1, bias=False),
        nn.BatchNorm2d(out_channels),
    )


class ResBlock(nn.Module):
    def __init__(self, in_channels, out_channels, stride=None):
        super().__init__()
        stride = stride or (1 if in_channels >= out_channels else 2)
        self.block = conv_block(in_channels, out_channels, stride)
        if stride == 1 and in_channels == out_channels:
            self.skip = nn.Identity()
        else:
            self.skip = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(out_channels),
            )

    def forward(self, x):
        return F.relu(self.block(x) + self.skip(x))


class ResNet(nn.Module):
    def __init__(self, in_channels, block_features, num_classes=10, headless=False):
        super().__init__()
        block_features = [block_features[0]] + block_features + ([num_classes] if headless else [])
        self.expand = nn.Sequential(
            nn.Conv2d(in_channels, block_features[0], kernel_size=1, stride=1, bias=False),
            nn.BatchNorm2d(block_features[0]),
        )
        self.res_blocks = nn.ModuleList([
            ResBlock(block_features[i], block_features[i + 1])
            for i in range(len(block_features) - 1)
        ])
        self.linear_head = None if headless else nn.Linear(block_features[-1], num_classes)

    def forward(self, x):
        x = self.expand(x)
        for res_block in self.res_blocks:
            x = res_block(x)
        if self.linear_head is not None:
            x = F.avg_pool2d(x, x.shape[-1])  # completely reduce spatial dimension
            x = self.linear_head(x.reshape(x.shape[0], -1))
        return x


def resnet18(in_channels, num_classes):
    block_features = [64] * 2 + [128] * 2 + [256] * 2 + [512] * 2
    return ResNet(in_channels, block_features, num_classes)


def resnet34(in_channels, num_classes):
    block_features = [64] * 3 + [128] * 4 + [256] * 6 + [512] * 3
    return ResNet(in_channels, block_features, num_classes)



class Stega(nn.Module):
    def __init__(self, nn1, nn2, decoder):
        super().__init__()

        self.nn1 = nn1
        self.nn2 = nn2
        self.decoder = decoder

    def nn1_work(self, x_s):
        """
        Return
        :param x:
        :return:
        """
        xs_hat = self.nn1(x_s)
        return xs_hat

    def forward(self, xs, xh):
        B, _ = xs.shape

        xs_hat = self.nn1(xs)
        combined_batch = torch.cat((xs_hat, xh), dim=1) # double the channel size

        xh_hat = self.nn2(combined_batch)  # output the host image, you can also call it cover image

        xs_hat2 = self.decoder(xh_hat) # recover xs

        return xh_hat, xs_hat2

    def decoder_imgae(self, xh_with_xs):
        xs_hat2 = self.decoder(xh_with_xs)
        return xs_hat2


def init_stega(args):
    if args.dataset == "MNIST":
        nn1 = LinearModel(n_feature=28*28, n_output=28*28)
        nn2 = LinearModel(n_feature=2*28*28, n_output=28*28)
        decoder = LinearModel(n_feature=28*28, n_output=28*28)

    stega = Stega(nn1, nn2, decoder)
    stega.to(args.device)
    return stega


class VIB(nn.Module):
    def __init__(self, encoder, approximator, decoder):
        super().__init__()

        self.encoder = encoder
        self.approximator = approximator
        self.decoder = decoder
        self.fc3 = nn.Linear(28*28, 28*28)  # output

    def explain(self, x, mode='topk'):
        """Returns the relevance scores
        """
        double_logits_z = self.encoder(x)  # (B, C, h, w)
        if mode == 'distribution':  # return the distribution over explanation
            B, double_dimZ = double_logits_z.shape
            dimZ = int(double_dimZ / 2)
            mu = double_logits_z[:, :dimZ].cuda()
            logvar = torch.log(torch.nn.functional.softplus(double_logits_z[:, dimZ:]).pow(2)).cuda()
            logits_z = self.reparametrize(mu, logvar)
            return logits_z, mu, logvar
        elif mode == 'test':  # return top k pixels from input
            B, double_dimZ = double_logits_z.shape
            dimZ = int(double_dimZ / 2)
            mu = double_logits_z[:, :dimZ].cuda()
            logvar = torch.log(torch.nn.functional.softplus(double_logits_z[:, dimZ:]).pow(2)).cuda()
            logits_z = self.reparametrize(mu, logvar)
            return logits_z

    def forward(self, x, mode='topk'):
        B = x.size(0)
        #         print("B, C, H, W", B, C, H, W)
        if mode == 'distribution':
            logits_z, mu, logvar = self.explain(x, mode='distribution')  # (B, C, H, W), (B, C* h* w)
            logits_y = self.approximator(logits_z)  # (B , 10)
            logits_y = logits_y.reshape((B, 10))  # (B,   10)
            return logits_z, logits_y, mu, logvar
        elif mode == '64QAM_distribution':
            logits_z, mu, logvar = self.explain(x, mode='distribution')  # (B, C, H, W), (B, C* h* w)
            # print(logits_z)

            logits_y = self.approximator(logits_z)  # (B , 10)
            logits_y = logits_y.reshape((B, 10))  # (B,   10)
            return logits_z, logits_y, mu, logvar

        elif mode == 'with_reconstruction':
            logits_z, mu, logvar = self.explain(x, mode='distribution')  # (B, C, H, W), (B, C* h* w)
            # print("logits_z, mu, logvar", logits_z, mu, logvar)
            logits_y = self.approximator(logits_z)  # (B , 10)
            logits_y = logits_y.reshape((B, 10))  # (B,   10)
            x_hat, x_m, x_inverse_m = self.reconstruction(logits_z, x)
            return logits_z, logits_y, x_hat, mu, logvar, x_m, x_inverse_m

        elif mode == 'VAE':
            logits_z, mu, logvar = self.explain(x, mode='distribution')  # (B, C, H, W), (B, C* h* w)
            # VAE is not related to labels
            # print("logits_z, mu, logvar", logits_z, mu, logvar)
            # logits_y = self.approximator(logits_z)  # (B , 10)
            # logits_y = logits_y.reshape((B, 10))  # (B,   10)
            x_hat = self.reconstruction(logits_z, x)
            return logits_z, x_hat, mu, logvar
        elif mode == 'test':
            logits_z = self.explain(x, mode=mode)  # (B, C, H, W)
            logits_y = self.approximator(logits_z)
            return logits_y

    def reconstruction(self, logits_z, x):
        B, dimZ = logits_z.shape
        logits_z = logits_z.reshape((B, -1))
        # x_out = self.fc2(logits_z)

        output_x = self.decoder(logits_z)
        # x_v = x.view(x.size(0), -1)
        x_m, x_inverse_m = apply_random_mask(x, 0.7)
        x_m = x_m.view(x_m.size(0), -1)
        output_x = output_x.view(output_x.size(0), -1)
        x2 = F.relu(x_m - output_x)

        return torch.sigmoid(self.fc3(x2)), x_m,x_inverse_m

    def cifar_recon(self, logits_z):
        # B, c, h, w = logits_z.shape
        # logits_z=logits_z.reshape((B,-1))
        output_x = self.reconstructor(logits_z)
        return torch.sigmoid(output_x)

    def reparametrize(self, mu, logvar):
        std = logvar.mul(0.5).exp_()
        if torch.cuda.is_available():
            eps = torch.cuda.FloatTensor(std.size()).normal_()
        else:
            eps = torch.FloatTensor(std.size()).normal_()
        eps = Variable(eps)
        return eps.mul(std).add_(mu)


def init_vib(args):
    if args.dataset == 'MNIST':
        approximator = LinearModel(n_feature=args.dimZ)
        decoder = LinearModel(n_feature=args.dimZ, n_output=28 * 28)
        encoder = resnet18(1, args.dimZ * 2)  # 64QAM needs 6 bits
        lr = args.lr

    elif args.dataset == 'CIFAR10':
        # approximator = resnet18(3, 10) #LinearModel(n_feature=args.dimZ)
        approximator = LinearModel(n_feature=args.dimZ)
        encoder = resnet18(3, args.dimZ * 2)  # resnet18(1, 49*2)
        decoder = Decoder() #LinearModel(n_feature= 3 * 32 * 32, n_output=3 * 32 * 32) # args.dimZ resnet18(2, 3 * 32 * 32) #
        lr = args.lr

    elif args.dataset == 'CIFAR100':
        approximator = LinearModel(n_feature=args.dimZ, n_output=100)
        encoder = resnet18(3, args.dimZ * 2)  # resnet18(1, 49*2)
        decoder = LinearModel(n_feature=args.dimZ, n_output=3 * 32 * 32)
        lr = args.lr

    elif args.dataset == 'CelebA':
        approximator = LinearModel(n_feature=args.dimZ, n_output=2)
        encoder = resnet18(3, args.dimZ * 2)  # resnet18(1, 49*2)
        decoder = Decoder() #LinearModel(n_feature=args.dimZ, n_output=3 * 32 * 32)
        lr = args.lr

    vib = VIB(encoder, approximator, decoder)
    vib.to(args.device)
    return vib, lr


def num_params(model):
    return sum([p.numel() for p in model.parameters() if p.requires_grad])


def vib_train(dataset, model, loss_fn, reconstruction_function, args, epoch, acc_list, mse_list, train_loader, train_type, dataloader_er_clean, dataloader_er_with_trigger):
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    for step, (x, y) in enumerate(dataset):
        x, y = x.to(args.device), y.to(args.device)  # (B, C, H, W), (B, 10)
        # x = x.view(x.size(0), -1)

        logits_z, logits_y, x_hat, mu, logvar, x_m, x_inverse_m = model(x, mode='with_reconstruction')  # (B, C* h* w), (B, N, 10)
        # VAE two loss: KLD + MSE

        H_p_q = loss_fn(logits_y, y)

        KLD_element = mu.pow(2).add_(logvar.exp()).mul_(-1).add_(1).add_(logvar).cuda()
        KLD = torch.sum(KLD_element).mul_(-0.5).cuda()
        KLD_mean = torch.mean(KLD_element).mul_(-0.5).cuda()

        x_hat = x_hat.view(x_hat.size(0), -1)
        x = x.view(x.size(0), -1)
        x_inverse_m = x_inverse_m.view(x_inverse_m.size(0),-1)
        # x = torch.sigmoid(torch.relu(x))
        BCE = reconstruction_function(x_hat, x)  # mse loss for vae # torch.mean((x_hat - x) ** 2 * (x_inverse_m > 0).int()) / 0.75 # reconstruction_function(x_hat, x_inverse_m)  # mse loss for vae

        # Calculate the L2-norm
        l2_norm_bce = torch.norm(args.beta * KLD_mean + args.mse_rate * BCE, p=2)

        l2_norm_hpq = torch.norm(args.beta * KLD_mean + H_p_q, p=2)

        total_u_s = l2_norm_bce + l2_norm_hpq
        bce_rate = l2_norm_bce / total_u_s
        hpq_rate = l2_norm_hpq / total_u_s

        '''purpose is to make the unlearning item =0, and the learning item =0 '''

        if train_type == 'FIXED':
            loss = args.beta * KLD_mean + args.mse_rate * BCE + H_p_q
        elif train_type == 'MULTI':
            loss = (args.beta * KLD_mean + args.mse_rate * BCE) * bce_rate + hpq_rate * (args.beta * KLD_mean + H_p_q)

        # loss = args.beta * KLD_mean + BCE  # / (args.batch_size * 28 * 28)

        optimizer.zero_grad()
        loss.backward()

        # torch.nn.utils.clip_grad_norm_(model.parameters(), 5, norm_type=2.0, error_if_nonfinite=False)
        optimizer.step()

        # acc = (logits_y.argmax(dim=1) == y).float().mean().item()
        sigma = torch.sqrt_(torch.exp(logvar)).mean().item()
        # JS_p_q = 1 - js_div(logits_y.softmax(dim=1), y.softmax(dim=1)).mean().item()
        metrics = {
            # 'acc': acc,
            'loss': loss.item(),
            'BCE': BCE.item(),
            'H(p,q)': H_p_q.item(),
            # '1-JS(p,q)': JS_p_q,
            'mu': torch.mean(mu).item(),
            'sigma': sigma,
            'KLD': KLD.item(),
            'KLD_mean': KLD_mean.item(),
        }
        # if epoch == args.num_epochs - 1:
        #     mu_list.append(torch.mean(mu).item())
        #     sigma_list.append(sigma)
        if step % len(train_loader) % 10000 == 0:
            print(f'[{epoch}/{0 + args.num_epochs}:{step % len(train_loader):3d}] '
                  + ', '.join([f'{k} {v:.3f}' for k, v in metrics.items()]))
            x_cpu = x.cpu().data
            x_cpu = x_cpu.clamp(0, 1)
            x_cpu = x_cpu.view(x_cpu.size(0), 1, 28, 28)
            grid = torchvision.utils.make_grid(x_cpu, nrow=4 )
            # plt.imshow(np.transpose(grid, (1, 2, 0)))  # 交换维度，从GBR换成RGB
            # plt.show()

            x_hat_cpu = x_hat.cpu().data
            x_hat_cpu = x_hat_cpu.clamp(0, 1)
            x_hat_cpu = x_hat_cpu.view(x_hat_cpu.size(0), 1, 28, 28)
            grid = torchvision.utils.make_grid(x_hat_cpu, nrow=4 )
            # plt.imshow(np.transpose(grid, (1, 2, 0)))  # 交换维度，从GBR换成RGB
            # plt.show()

    return model, acc_list, mse_list

def continue_vib_train(dataset, model, loss_fn, reconstruction_function, args, epoch, acc_list, mse_list, train_loader, train_type, dataloader_er_clean, dataloader_er_with_trigger):
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    for step, (x, y) in enumerate(dataset):
        x, y = x.to(args.device), y.to(args.device)  # (B, C, H, W), (B, 10)
        # x = x.view(x.size(0), -1)

        logits_z, logits_y, x_hat, mu, logvar, x_m, x_inverse_m = model(x, mode='with_reconstruction')  # (B, C* h* w), (B, N, 10)
        # VAE two loss: KLD + MSE

        H_p_q = loss_fn(logits_y, y)

        KLD_element = mu.pow(2).add_(logvar.exp()).mul_(-1).add_(1).add_(logvar).cuda()
        KLD = torch.sum(KLD_element).mul_(-0.5).cuda()
        KLD_mean = torch.mean(KLD_element).mul_(-0.5).cuda()

        x_hat = x_hat.view(x_hat.size(0), -1)
        x = x.view(x.size(0), -1)
        x_inverse_m = x_inverse_m.view(x_inverse_m.size(0),-1)
        # x = torch.sigmoid(torch.relu(x))
        BCE = reconstruction_function(x_hat, x)  # mse loss for vae # torch.mean((x_hat - x) ** 2 * (x_inverse_m > 0).int()) / 0.75 # reconstruction_function(x_hat, x_inverse_m)  # mse loss for vae

        # Calculate the L2-norm
        l2_norm_bce = torch.norm(args.beta * KLD_mean + args.mse_rate * BCE, p=2)

        l2_norm_hpq = torch.norm(args.beta * KLD_mean + H_p_q, p=2)

        total_u_s = l2_norm_bce + l2_norm_hpq
        bce_rate = l2_norm_bce / total_u_s
        hpq_rate = l2_norm_hpq / total_u_s

        '''purpose is to make the unlearning item =0, and the learning item =0 '''

        if train_type == 'FIXED':
            loss = args.beta * KLD_mean + args.mse_rate * BCE + H_p_q
        elif train_type == 'MULTI':
            loss = (args.beta * KLD_mean + args.mse_rate * BCE) * bce_rate + hpq_rate * (args.beta * KLD_mean + H_p_q)

        # loss = args.beta * KLD_mean + BCE  # / (args.batch_size * 28 * 28)

        optimizer.zero_grad()
        loss.backward()

        # torch.nn.utils.clip_grad_norm_(model.parameters(), 5, norm_type=2.0, error_if_nonfinite=False)
        optimizer.step()

        # acc = (logits_y.argmax(dim=1) == y).float().mean().item()
        sigma = torch.sqrt_(torch.exp(logvar)).mean().item()
        # JS_p_q = 1 - js_div(logits_y.softmax(dim=1), y.softmax(dim=1)).mean().item()
        metrics = {
            # 'acc': acc,
            'loss': loss.item(),
            'BCE': BCE.item(),
            'H(p,q)': H_p_q.item(),
            # '1-JS(p,q)': JS_p_q,
            'mu': torch.mean(mu).item(),
            'sigma': sigma,
            'KLD': KLD.item(),
            'KLD_mean': KLD_mean.item(),
        }
        # if epoch == args.num_epochs - 1:
        #     mu_list.append(torch.mean(mu).item())
        #     sigma_list.append(sigma)
        if step % len(train_loader) % 10000 == 0:
            print(f'[{epoch}/{0 + args.num_epochs}:{step % len(train_loader):3d}] '
                  + ', '.join([f'{k} {v:.3f}' for k, v in metrics.items()]))
            x_cpu = x.cpu().data
            x_cpu = x_cpu.clamp(0, 1)
            x_cpu = x_cpu.view(x_cpu.size(0), 1, 28, 28)
            grid = torchvision.utils.make_grid(x_cpu, nrow=4 )
            # plt.imshow(np.transpose(grid, (1, 2, 0)))  # 交换维度，从GBR换成RGB
            # plt.show()

            x_hat_cpu = x_hat.cpu().data
            x_hat_cpu = x_hat_cpu.clamp(0, 1)
            x_hat_cpu = x_hat_cpu.view(x_hat_cpu.size(0), 1, 28, 28)
            grid = torchvision.utils.make_grid(x_hat_cpu, nrow=4 )
            # plt.imshow(np.transpose(grid, (1, 2, 0)))  # 交换维度，从GBR换成RGB
            # plt.show()

    for step, (x, y) in enumerate(dataloader_er_clean):
        x, y = x.to(args.device), y.to(args.device)  # (B, C, H, W), (B, 10)
        # x = x.view(x.size(0), -1)

        logits_z, logits_y, x_hat, mu, logvar, x_m, x_inverse_m = model(x, mode='with_reconstruction')  # (B, C* h* w), (B, N, 10)
        H_p_q = loss_fn(logits_y, y)

        # acc_list.append(H_p_q.item())

        x_hat = x_hat.view(x_hat.size(0), -1)
        x = x.view(x.size(0), -1)
        x_inverse_m = x_inverse_m.view(x_inverse_m.size(0),-1)
        BCE = reconstruction_function(x_hat, x)  # mse loss for vae

    for step, (x, y) in enumerate(dataloader_er_with_trigger):
        x, y = x.to(args.device), y.to(args.device)  # (B, C, H, W), (B, 10)
        # x = x.view(x.size(0), -1)

        logits_z, logits_y, x_hat, mu, logvar, x_m, x_inverse_m = model(x, mode='with_reconstruction')  # (B, C* h* w), (B, N, 10)
        H_p_q = loss_fn(logits_y, y)

        x_hat = x_hat.view(x_hat.size(0), -1)
        x = x.view(x.size(0), -1)
        x_inverse_m = x_inverse_m.view(x_inverse_m.size(0),-1)
        BCE = reconstruction_function(x_hat, x)  # mse loss for va

        # mse_list.append(BCE.item())

    return model, acc_list, mse_list


def plot_latent(autoencoder, data_loader, args, num_batches=100):
    for i, (x, y) in enumerate(data_loader):
        # x = x.view(x.size(0), -1)
        z, x_hat, mu, logvar = autoencoder(x.to(args.device), mode='VAE')
        z = z.to('cpu').detach().numpy()
        y = y.to('cpu')
        plt.scatter(z[:, 0], z[:, 1], c=y, cmap='tab10')
        if i > num_batches:
            plt.colorbar()
            break


def plot_reconstructed(autoencoder, r0=(-5, 10), r1=(-10, 5), n=12):
    w = 28
    img = np.zeros((n * w, n * w))
    for i, y in enumerate(np.linspace(*r1, n)):
        for j, x in enumerate(np.linspace(*r0, n)):
            z = torch.Tensor([[x, y]]).to(device)
            x_hat = autoencoder.reconstruction(z, x)
            x_hat = x_hat.reshape(28, 28).to('cpu').detach().numpy()
            img[(n - 1 - i) * w:(n - 1 - i + 1) * w, j * w:(j + 1) * w] = x_hat
    plt.imshow(img, extent=[*r0, *r1])


def create_backdoor_train_dataset(dataname, train_data, base_label, trigger_label, poison_samples, batch_size, args,
                                  add_backdoor, dp_sample):
    train_data = PoisonedDataset(train_data, base_label, trigger_label, poison_samples=poison_samples, mode="train",
                                 device=args.device, dataname=dataname, args=args, add_backdoor=add_backdoor,
                                 dp_sample=dp_sample)
    b = Data.TensorDataset(train_data.data, train_data.targets)
    # x = test_data_tri.data_test[0]
    x = torch.tensor(train_data.data[0])
    # print(x)
    x = x.cpu().data
    x = x.clamp(0, 1)
    if args.dataset == "MNIST":
        x = x.view(x.size(0), 1, 28, 28)
    elif args.dataset == "CIFAR10":
        x = x.view(1, 3, 32, 32)
    print(x)
    grid = torchvision.utils.make_grid(x, nrow=1 )
    plt.imshow(np.transpose(grid, (1, 2, 0)))  # 交换维度，从GBR换成RGB
    plt.show()
    return train_data.data, train_data.targets



def linear_train(data_loader, vib_full_trained, model, loss_fn, args):
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    vib_full_trained.eval()
    for step, (x, y) in enumerate(data_loader):
        x, y = x.to(args.device), y.to(args.device)  # (B, C, H, W), (B, 10)

        x = x.view(x.size(0), -1)
        # x_hat = x_hat.view(x_hat.size(0), -1)
        logits_y = model(x.detach())  # (B, C* h* w), (B, N, 10)
        H_p_q = loss_fn(logits_y, y)

        loss = H_p_q

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5, norm_type=2.0, error_if_nonfinite=False)
        optimizer.step()

        acc = (logits_y.argmax(dim=1) == y).float().mean().item()

        metrics = {
            'acc': acc,
            'loss': loss.item(),
            'H(p,q)': H_p_q.item(),
            # '1-JS(p,q)': JS_p_q,
            # 'mu': torch.mean(mu).item(),
            # 'sigma': sigma,
            # 'KLD': KLD.item(),
            # 'KLD_mean': KLD_mean.item(),
        }

        if step % len(data_loader) % 600 == 0:
            print(f'[{epoch}/{0 + args.num_epochs}:{step % len(data_loader):3d}] '
                  + ', '.join([f'{k} {v:.3f}' for k, v in metrics.items()]))
    return model


@torch.no_grad()
def test_linear_acc(model, data_loader, args, name='test', epoch=999):
    num_total = 0
    num_correct = 0
    model.eval()
    for x, y in data_loader:
        x, y = x.to(args.device), y.to(args.device)
        x = x.view(x.size(0), -1)
        out = model(x)
        # print(y, out)
        if y.ndim == 2:
            y = y.argmax(dim=1)
        num_correct += (out.argmax(dim=1) == y).sum().item()
        num_total += len(x)
    acc = num_correct / num_total
    acc = round(acc, 5)
    print(f'epoch {epoch}, {name} accuracy:  {acc:.4f}')
    return acc

@torch.no_grad()
def infer_linear_from_vib_acc(model, vib, data_loader, args, name='test', epoch=999):
    num_total = 0
    num_correct = 0
    model.eval()
    for x, y in data_loader:
        x, y = x.to(args.device), y.to(args.device)
        x = x.view(x.size(0), -1)
        out = model(x)
        # print(y, out)
        if y.ndim == 2:
            y = y.argmax(dim=1)
        num_correct += (out.argmax(dim=1) == 0).sum().item()
        num_total += len(x)
    acc = num_correct / num_total
    acc = round(acc, 5)
    print(f'epoch {epoch}, {name} accuracy:  {acc:.4f}')
    return acc

@torch.no_grad()
def eva_vae_generation(vib, classifier_model, dataloader_erase, args, name='test', epoch=999):
    # first, generate x_hat from trained vae
    vib.eval()
    classifier_model.eval()
    num_total = 0
    num_correct = 0
    for batch_idx, (x, y) in enumerate(dataloader_erase):
        x, y = x.to(args.device), y.to(args.device)  # (B, C, H, W), (B, 10)
        # x = x.view(x.size(0), -1)
        logits_z, x_hat, mu, logvar = vib(x, mode='VAE')  # (B, C* h* w), (B, N, 10)

        x_hat = x_hat.view(x_hat.size(0), -1)
        # second, input the x_hat to classifier
        logits_y = classifier_model(x_hat.detach())
        if y.ndim == 2:
            y = y.argmax(dim=1)
        num_correct += (logits_y.argmax(dim=1) == y).sum().item()
        num_total += len(x)
        if batch_idx == 0:
            x_hat_cpu = x_hat.cpu().data
            x_hat_cpu = x_hat_cpu.clamp(0, 1)
            x_hat_cpu = x_hat_cpu.view(x_hat_cpu.size(0), 1, 28, 28)
            grid = torchvision.utils.make_grid(x_hat_cpu, nrow=4 )
            # plt.imshow(np.transpose(grid, (1, 2, 0)))  # 交换维度，从GBR换成RGB
            # plt.show()

    acc = num_correct / num_total
    acc = round(acc, 5)
    print(f'epoch {epoch}, {name} accuracy:  {acc:.4f}')
    return acc


@torch.no_grad()
def eva_vib(vib, dataloader_erase, args, name='test', epoch=999):
    # first, generate x_hat from trained vae
    vib.eval()

    num_total = 0
    num_correct = 0
    for batch_idx, (x, y) in enumerate(dataloader_erase):
        x, y = x.to(args.device), y.to(args.device)  # (B, C, H, W), (B, 10)
        # x = x.view(x.size(0), -1)
        # print(x.shape)
        logits_z, logits_y, x_hat, mu, logvar, x_m, x_inverse_m = vib(x, mode='with_reconstruction')  # (B, C* h* w), (B, N, 10)

        x_hat = x_hat.view(x_hat.size(0), -1)

        if y.ndim == 2:
            y = y.argmax(dim=1)
        num_correct += (logits_y.argmax(dim=1) == y).sum().item()
        num_total += len(x)

    acc = num_correct / num_total
    acc = round(acc, 5)
    print(f'epoch {epoch}, {name} accuracy:  {acc:.4f}')
    return acc

def show_mse_of_backdoor(x,recons_f):
    x2 = x.clone()
    x2 = x2.view(1, 28, 28)
    _, width, height = x2.shape
    x2[:, width - 3, height - 3] = 1
    x2[:, width - 3, height - 4] = 1
    x2[:, width - 4, height - 3] = 1
    x2[:, width - 4, height - 4] = 1
    x2 = x2.view(1, -1)

    MSE_x2_hat2 = recons_f(x2, x)

    print(MSE_x2_hat2.item())

def unlearning_vae(vib, args, dataloader_erase, dataloader_remain, reconstruction_function, classifier_model,
                   train_type):
    vib_unl, lr = init_vib(args)
    vib_unl.to(args.device)
    vib_unl.load_state_dict(vib.state_dict())
    optimizer_unl = torch.optim.Adam(vib_unl.parameters(), lr=lr)

    print(len(dataloader_erase.dataset))
    train_bs = 0

    for epoch in range(args.num_epochs):
        vib_unl.train()
        batch_idx = 0
        for (x, y), (x2, y2) in zip(dataloader_erase, dataloader_remain):
            x, y = x.to(args.device), y.to(args.device)  # (B, C, H, W), (B, 10)
            if args.dataset == 'MNIST':
                x = x.view(x.size(0), -1)

            x2, y2 = x2.to(args.device), y2.to(args.device)  # (B, C, H, W), (B, 10)
            if args.dataset == 'MNIST':
                x2 = x2.view(x2.size(0), -1)

            logits_z_e, x_hat_e, mu_e, logvar_e = vib_unl(x, mode='VAE')
            logits_z_e2, x_hat_e2, mu_e2, logvar_e2 = vib_unl(x2, mode='VAE')

            logits_z_f, x_hat_f, mu_f, logvar_f = vib(x, mode='VAE')

            logits_z_e_log_softmax = logits_z_e.log_softmax(dim=1)
            p_x_e = x.softmax(dim=1)
            B = x.size(0)

            KLD_element2 = mu_e2.pow(2).add_(logvar_e2.exp()).mul_(-1).add_(1).add_(logvar_e2).to(args.device)
            KLD_mean2 = torch.mean(KLD_element2).mul_(-0.5).to(args.device)

            KLD = 0.5 * torch.mean(
                logvar_f - logvar_e + (torch.exp(logvar_e) + (mu_e - mu_f).pow(2)) / torch.exp(logvar_f) - 1).cuda()

            # KLD between erased z and original z
            KLD_mean = 0.5 * torch.mean(
                logvar_f - logvar_e + (torch.exp(logvar_e) + (mu_e - mu_f).pow(2)) / torch.exp(logvar_f) - 1).cuda()

            KL_z_r = (torch.exp(logits_z_e_log_softmax) * logits_z_e_log_softmax).sum(dim=1).mean() + math.log(
                logits_z_e_log_softmax.shape[1])

            # x_hat_e = x_hat_e.view(x_hat_e.size(0), -1)
            # x_hat_e = torch.sigmoid(reconstructor(logits_z_e))
            x_hat_e = x_hat_e.view(x_hat_e.size(0), -1)
            x_hat_e2 = x_hat_e2.view(x_hat_e2.size(0), -1)

            x = x.view(x.size(0), -1)
            # x = torch.sigmoid(x)
            BCE = reconstruction_function(x_hat_e, x)  # mse loss = - log p = log 1/p
            BCE2 = reconstruction_function(x_hat_e2, x2)
            # BCE = torch.mean(x_hat_e.log_softmax(dim=1))
            e_log_p = torch.exp(BCE / (args.batch_size * 28 * 28))  # = 1/p

            log_z = torch.mean(logits_z_e.log_softmax(dim=1))

            kl_loss = nn.KLDivLoss(reduction="batchmean", log_target=True)

            # Calculate the L2-norm
            l2_norm_unl = torch.norm(args.kld_to_org * KLD_mean - args.unlearn_bce * BCE, p=2)

            l2_norm_ss = torch.norm(args.self_sharing_rate * (args.beta * KLD_mean2 + BCE2), p=2)

            total_u_s = l2_norm_unl + l2_norm_ss
            unl_rate = l2_norm_unl / total_u_s
            self_s_rate = l2_norm_ss / total_u_s

            # unlearning_item = args.kld_to_org * KLD_mean.item() - args.unlearn_bce * BCE.item() # - args.reverse_rate * (log_z.item() )
            #
            # #print(unlearning_item)
            # learning_item = args.self_sharing_rate * (args.beta * KLD_mean2.item() + BCE2.item())
            # #print(learning_item)
            #
            # total = unlearning_item + learning_item # expected to equal to 0
            # if unlearning_item <= 0:# have approixmate to the retrained distribution and no need to unlearn
            #     unl_rate = 0
            # else:
            #     unl_rate = unlearning_item / total
            #
            # self_s_rate = 1 - unl_rate

            '''purpose is to make the unlearning item =0, and the learning item =0 '''

            if train_type == 'VAE_unl':
                loss = args.kld_to_org * KLD_mean - args.unlearn_bce * BCE
            elif train_type == 'VAE_unl_ss':
                loss = (args.kld_to_org * KLD_mean - args.unlearn_bce * BCE) * unl_rate + self_s_rate * args.self_sharing_rate * (
                               args.beta * KLD_mean2 + BCE2)  # args.beta * KLD_mean - H_p_q + args.beta * KLD_mean2  + H_p_q2 #- log_z / e_log_py #-   # H_p_q + args.beta * KLD_mean2

            optimizer_unl.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(vib_unl.parameters(), 5, norm_type=2.0, error_if_nonfinite=False)
            optimizer_unl.step()

            metrics = {
                # 'unlearning_item': unlearning_item,
                # 'learning_item': learning_item,
                # 'acc': acc,
                'loss': loss.item(),
                'BCE': BCE.item(),
                'l2_norm_unl': l2_norm_unl,
                'l2_norm_ss': l2_norm_ss,
                # 'H(p,q)': H_p_q.item(),
                # 'kl_f_e': kl_f_e.item(),
                # 'H_p_q2': H_p_q2.item(),
                # '1-JS(p,q)': JS_p_q,
                # 'mu_e': torch.mean(mu_e).item(),
                # 'sigma_e': torch.sqrt_(torch.exp(logvar_e)).mean().item(),
                'KLD': KLD.item(),
                'e_log_p': e_log_p.item(),
                'log_z': log_z.item(),
                'KLD_mean': KLD_mean.item(),
            }

            # if epoch == args.num_epochs - 1:
            #     mu_list.append(torch.mean(mu_e).item())
            #     sigma_list.append(torch.sqrt_(torch.exp(logvar_e)).mean().item())
            if batch_idx % len(dataloader_erase) % 600 == 0:
                print(f'[{epoch}/{0 + args.num_epochs}:{batch_idx % len(dataloader_erase):3d}] '
                      + ', '.join([f'{k} {v:.3f}' for k, v in metrics.items()]))
            batch_idx = batch_idx + 1
            train_bs = train_bs + 1
            # if acc_back < 0.05:
            #     break

        vib_unl.eval()

        valid_acc = eva_vae_generation(vib_unl, classifier_model, dataloader_erase, args, name='test', epoch=epoch)

        if valid_acc < 0.02:
            print()
            print("end unlearn, train_bs", train_bs)
            # break
    return vib_unl


def get_grad_dataset(model, dataset_loader, erasing_size):
    dim_z = 10*90
    temp_img = torch.empty(0, 1, 28, 28).float().to(args.device)
    temp_grad = torch.empty(0, dim_z).float().to(args.device)

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    total_loss = 0
    count_index = 0
    count_loss = 0
    for step, (x, y) in enumerate(dataset_loader):
        x, y = x.to(args.device), y.to(args.device)  # (B, C, H, W), (B, 10)
        if count_index >= erasing_size*2:
            break
        image = x
        logits_z, logits_y, x_hat, mu, logvar, x_m, x_inverse_m = model(x, mode='with_reconstruction')  # (B, C* h* w), (B, N, 10)
        # VAE two loss: KLD + MSE

        H_p_q = loss_fn(logits_y, y)

        KLD_element = mu.pow(2).add_(logvar.exp()).mul_(-1).add_(1).add_(logvar).cuda()
        KLD = torch.sum(KLD_element).mul_(-0.5).cuda()
        KLD_mean = torch.mean(KLD_element).mul_(-0.5).cuda()

        x_hat = x_hat.view(x_hat.size(0), -1)
        x = x.view(x.size(0), -1)
        x_inverse_m = x_inverse_m.view(x_inverse_m.size(0),-1)
        # x = torch.sigmoid(torch.relu(x))
        BCE = reconstruction_function(x_hat, x)  # mse loss for vae

        # Calculate the L2-norm
        l2_norm_bce = torch.norm(args.beta * KLD_mean + args.mse_rate * BCE, p=2)

        l2_norm_hpq = torch.norm(args.beta * KLD_mean + H_p_q, p=2)

        total_u_s = l2_norm_bce + l2_norm_hpq
        bce_rate = l2_norm_bce / total_u_s
        hpq_rate = l2_norm_hpq / total_u_s

        '''purpose is to make the unlearning item =0, and the learning item =0 '''

        loss = (args.beta * KLD_mean + args.mse_rate * BCE) * bce_rate + hpq_rate * (args.beta * KLD_mean + H_p_q)

        # loss = args.beta * KLD_mean + BCE  # / (args.batch_size * 28 * 28)

        optimizer.zero_grad()
        loss.backward()
        total_loss += loss.item()
        count_loss += 1
        # torch.nn.utils.clip_grad_norm_(model.parameters(), 5, norm_type=2.0, error_if_nonfinite=False)

        for name, param in model.named_parameters():
            # print(name, param.shape)
            # if name == 'encoder.linear_head.weight':
            #     print(param)

            if name == 'approximator.fc2.weight':
                # print(param)
                temp_img = torch.cat([temp_img, image], dim=0)
                t_grad = param.grad.view(1, -1)
                n, m = t_grad.size()
                B, C, H, W  = image.size()

                mean = 1  # Mean of the distribution
                std_dev = 0.2  # Standard deviation of the distribution

                # Generate Gaussian noise
                random_tensor = torch.randn(B, dim_z) * std_dev + mean
                random_tensor = random_tensor.cuda()
                # random_tensor = torch.rand(B, dim_z).cuda()
                scaled_random_tensor = random_tensor / random_tensor.sum() * B * dim_z


                for scale_v in scaled_random_tensor:
                    mean_t_grad = t_grad.mean()
                    std_t_grad = t_grad.std()
                    t_grad = t_grad * scale_v
                    # noise = torch.randn(n, dim_z-m).float().to(args.device)
                    # noise = noise * std_t_grad + mean_t_grad
                    # concatenated = torch.cat([t_grad, noise], dim=1)
                                        # print(noise)
                                        # print(t_grad)
                                        # break
                    # we need to ensure each image sample has the grad, even if now the grad is the combination of all unlearned samples
                    temp_grad = torch.cat([temp_grad, t_grad], dim=0)
                    count_index += 1

    #optimizer.step()
    # print("total_loss", total_loss)
    total_loss = total_loss / count_loss
    return temp_grad, temp_img, total_loss

@torch.no_grad()
def get_avg_recon_MSE(model, vib, test_loader, reconstruction_function, data_name):
    # Calculate average MSE over the test dataset
    vib.decoder.trainable = False
    vib.fc3.trainable = False
    reconstruction_function = nn.MSELoss(size_average=False)

    temp_img = torch.empty(0, 1, 28, 28).float().to(args.device)

    total_mse = 0.0
    total_cosine_simi = 0.0
    for grad, img in test_loader:
        grad, img = grad.to(args.device), img.to(args.device)  # (B, C, H, W), (B, 10)
        grad = grad.view(grad.size(0), 1, 30, 30)
        outputs = model(grad)
        x_hat,x_m,x_inverse_m = vib.reconstruction(outputs, img)
        img = img.view(img.size(0), -1)  # Flatten the images
        x_inverse_m = x_inverse_m.view(x_inverse_m.size(0),-1)
      #  loss = reconstruction_function(x_hat*(x_inverse_m > 0).int(), img*(x_inverse_m > 0).int())
        loss = reconstruction_function(x_hat  , img  )
        total_mse += loss.item()
        cos_sim = cosine_similarity(x_hat, img)
        total_cosine_simi += cos_sim.mean().item()

        grad = grad.view(grad.size(0), -1)
        B, Z_size = grad.shape
        x_hat = x_hat.view(x_hat.size(0), 1, 28, 28)
        temp_img = torch.cat([temp_img, x_hat], dim=0)

    average_mse = total_mse / len(test_loader)
    average_sim = total_cosine_simi / len(test_loader)
    # print(f'{data_name} Average Decoding MSE: {average_mse}')
    return average_mse, average_sim, temp_img

def train_reconstructor(vib, train_loader, reconstruction_function, args):
    # init reconsturctor
    # reconstructor = LinearModel(n_feature=40, n_output=28 * 28).to(args.device)
    vib.decoder.trainable = False
    vib.fc3.trainable = False

    reconstructor = resnet18(1, args.dimZ).to(args.device)
    optimizer_recon = torch.optim.Adam(reconstructor.parameters(), lr=args.lr)
    reconstructor.train()
    epochs = 1
    for epoch in range(args.num_epochs_recon):
        for grad, img in train_loader:
            grad, img = grad.to(args.device), img.to(args.device)  # (B, C, H, W), (B, 10)
            grad = grad.view(grad.size(0), 1, 30, 30)
            # img = img.view(img.size(0), -1)  # Flatten the images
            output = reconstructor(grad)
            # output = output.view(output.size(0), 3, 32, 32)
            x_hat,x_m,x_inverse_m = vib.reconstruction(output, img)
            img = img.view(img.size(0), -1)  # Flatten the images
            loss = reconstruction_function(x_hat, img)

            optimizer_recon.zero_grad()
            loss.backward()
            optimizer_recon.step()

        print(f'Epoch [{epoch + 1}/{epochs}], Loss: {loss.item():.4f}')

    return reconstructor


def infer_in_or_not(vib_full_trained, reconstructor_bac, classifier_model, er_with_trigger_train_loader):
    vib_full_trained.eval()
    reconstructor_bac.eval()
    classifier_model.eval()
    num_total = 0
    num_correct = 0
    for batch_idx, (grad, img) in enumerate(er_with_trigger_train_loader):
        grad, img = grad.to(args.device), img.to(args.device)  # (B, C, H, W), (B, 10)
        # x = x.view(x.size(0), -1)
        grad = grad.view(grad.size(0), 1, 30, 30)
        outputs = reconstructor_bac(grad)
        x_hat,x_m,x_inverse_m = vib_full_trained.reconstruction(outputs, img)
        x_hat = x_hat.view(x_hat.size(0), -1)
        # second, input the x_hat to classifier
        logits_y = classifier_model(x_hat.detach())

        num_correct += (logits_y.argmax(dim=1) == 0).sum().item()
        num_total += len(grad)
        if batch_idx == 0:
            x_hat_cpu = x_hat.cpu().data
            x_hat_cpu = x_hat_cpu.clamp(0, 1)
            x_hat_cpu = x_hat_cpu.view(x_hat_cpu.size(0), 1, 28, 28)
            grid = torchvision.utils.make_grid(x_hat_cpu, nrow=4)
            # plt.imshow(np.transpose(grid, (1, 2, 0)))  # 交换维度，从GBR换成RGB
            # plt.show()

    acc = num_correct / num_total
    acc = round(acc, 5)
    print(f'accuracy not in the remaining:  {acc:.4f}')
    return acc



seed = 0
torch.cuda.manual_seed_all(seed)
torch.manual_seed(seed)
random.seed(seed)
np.random.seed(seed)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

# torch.use_deterministic_algorithms(True)

# parse args
args = args_parser()
args.gpu = 0
# args.num_users = 10
args.device = torch.device('cuda:{}'.format(args.gpu) if torch.cuda.is_available() and args.gpu != -1 else 'cpu')
args.iid = True
args.model = 'z_linear'
args.num_epochs = 10 #10 # 10
args.num_epochs_recon = 50 # 50
args.dataset = 'MNIST'
args.add_noise = False
args.beta = 0.0001
args.mse_rate = 10
args.lr = 0.0001
args.dimZ = 128 # 40 #2
args.batch_size = 16
args.erased_local_r = 0.05 # the erased data ratio
args.unl_samples_size = 100
args.train_type = "MULTI"
args.kld_to_org = 1
args.unlearn_bce = 0.3
args.self_sharing_rate = 1
args.laplace_scale = 0

# print('args.beta', args.beta, 'args.lr', args.lr)

print('\n'.join(f'{k}={v}' for k, v in vars(args).items()))

device = args.device
print("device", device)

if args.dataset == 'MNIST':
    transform = T.Compose([
        T.ToTensor()
        # transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
    ])
    trans_mnist = transforms.Compose([transforms.ToTensor(), ])
    train_set = MNIST('../data/mnist', train=True, transform=trans_mnist, download=True)
    test_set = MNIST('../data/mnist', train=False, transform=trans_mnist, download=True)
    train_set_no_aug = train_set
elif args.dataset == 'CIFAR10':
    train_transform = T.Compose([#T.RandomCrop(32, padding=4),
                                 T.ToTensor(),
                                 ])  # T.Normalize((0.4914, 0.4822, 0.4465), (0.2464, 0.2428, 0.2608)),                                 T.RandomHorizontalFlip(),
    test_transform = T.Compose([T.ToTensor(),
                                ])  # T.Normalize((0.4914, 0.4822, 0.4465), (0.2464, 0.2428, 0.2608))
    train_set = CIFAR10('../data/cifar', train=True, transform=train_transform, download=True)
    test_set = CIFAR10('../data/cifar', train=False, transform=test_transform, download=True)
    train_set_no_aug = CIFAR10('../data/cifar', train=True, transform=test_transform, download=True)
elif args.dataset == 'CIFAR100':
    train_transform = T.Compose([#T.RandomCrop(32, padding=4),
                                 T.ToTensor(),
                                 ])  # T.Normalize((0.4914, 0.4822, 0.4465), (0.2464, 0.2428, 0.2608)),                                 T.RandomHorizontalFlip(),
    test_transform = T.Compose([T.ToTensor(),
                                ])  # T.Normalize((0.4914, 0.4822, 0.4465), (0.2464, 0.2428, 0.2608))
    train_set = CIFAR100('../data/cifar', train=True,  transform=train_transform, download=True)
    test_set = CIFAR100('../data/cifar', train=False, transform=test_transform, download=True)
elif args.dataset == 'CelebA':
    train_transform = T.Compose([T.Resize((32, 32)),
                                 T.ToTensor(),
                                 ])  # T.Normalize((0.4914, 0.4822, 0.4465), (0.2464, 0.2428, 0.2608)),                                 T.RandomHorizontalFlip(),
    test_transform = T.Compose([T.ToTensor(),
                                ])  # T.Normalize((0.4914, 0.4822, 0.4465), (0.2464, 0.2428, 0.2608))
    #/kaggle/input/celeba/
    data_path = '/kaggle/input/celeba'
    train_set = CelebA(data_path, split='train', target_type = 'attr', transform=train_transform, download=False)
    test_set = CelebA(data_path, split='test', target_type = 'attr', transform=train_transform, download=False)

# /kaggle/input/celeba
# ../data/CelebA

train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True, num_workers=1)
test_loader = DataLoader(test_set, batch_size=args.batch_size, shuffle=False, num_workers=1)

full_size = len(train_set)

erasing_size = int(full_size * args.erased_local_r)
remaining_size = full_size - erasing_size

remaining_set, erasing_set = torch.utils.data.random_split(train_set, [remaining_size, erasing_size])

re_erasing_set, the_unlearned_samples = torch.utils.data.random_split(erasing_set, [erasing_size - args.unl_samples_size, args.unl_samples_size])


re_re_set, er_on_remaining_set = torch.utils.data.random_split(remaining_set, [remaining_size - erasing_size, erasing_size])


print(len(remaining_set))
print(len(remaining_set.dataset.data))

# remaining_subset = My_subset(remaining_set.dataset, remaining_set.indices)
# erasing_subset = My_subset(erasing_set.dataset, erasing_set.indices)

dataloader_remain = DataLoader(re_re_set, batch_size=args.batch_size, shuffle=True) # when using remaining_set, means including the erased samples in the remaining dataset

# if we don't use poisoned set, we use full set
dataloader_erased = DataLoader(erasing_set, batch_size=args.batch_size, shuffle=True)

# Assuming train_loader1 and train_loader2 are your data loaders
dataset1 = dataloader_remain.dataset
dataset2 = dataloader_erased.dataset

# Concatenate datasets and create a new loader
combined_dataset = ConcatDataset([dataset1, dataset2])
combined_loader = DataLoader(combined_dataset, batch_size=args.batch_size, shuffle=True)



########################################################################
## add trigger


## add to one class

add_backdoor = 1  # =1 add backdoor , !=1 not add
# reshaped_data = data_reshape_to_np(erasing_subset, dataname=args.dataset)
poison_samples = erasing_size # len(erasing_subset.data)
mode = "train"
# feature_extra = SimpleCNN().cuda()

erased_set_with_tri = add_trigger_new(add_backdoor, dataset2, poison_samples, mode, args)
erased_on_rem_with_tri = add_trigger_new(add_backdoor, er_on_remaining_set, poison_samples, mode, args)

the_unl_sampe_with_tri =  add_trigger_new(add_backdoor, the_unlearned_samples, poison_samples, mode, args)

poison_samples = int(full_size) * args.erased_local_r

x, y = erased_set_with_tri[1]

# print(x)
x = x.cpu().data
x = x.clamp(0, 1)
if args.dataset == "MNIST":
    x = x.view(x.size(0), 1, 28, 28)
elif args.dataset == "CIFAR10":
    x = x.view(1, 3, 32, 32)
elif args.dataset == "CelebA":
    x = x.view(1, 3, 32, 32)
print(x)
grid = torchvision.utils.make_grid(x, nrow=1)
# plt.imshow(np.transpose(grid, (1, 2, 0)))  # 交换维度，从GBR换成RGB
# plt.show()





# seems here the batch size should be 1 for gradients achieving, can could be erasing_size for group of samples unlearning
# clean erased samples, still have similar samples in the remaining dataset

# here. the batch size is the unlearning samples size, because we collect the update as the difference for the unlearning operation.
unlearning_s_size = args.unl_samples_size

dataloader_er_clean_on_re = DataLoader(er_on_remaining_set, batch_size=unlearning_s_size, shuffle=True)

# samples on remaining set with backdoor
dataloader_on_re_with_trigger = DataLoader(erased_on_rem_with_tri, batch_size=unlearning_s_size, shuffle=True)


# clean erased samples not in the remaining dataset
dataloader_er_clean = DataLoader(erasing_set, batch_size=unlearning_s_size, shuffle=True)

# samples with backdoor trigger, not in the remainig dataset.
dataloader_er_with_trigger = DataLoader(erased_set_with_tri, batch_size=unlearning_s_size, shuffle=True)


# Concatenate datasets and create a new loader
poison_trainset = ConcatDataset([dataset1, the_unl_sampe_with_tri])


# remaining dataset for retraining the model
# dataloader_remain = DataLoader(dataset1, batch_size=args.batch_size, shuffle=True)

# if we don't use poisoned set, we use full set
dataloader_full = DataLoader(poison_trainset, batch_size=args.batch_size, shuffle=True)



# print(len(dataloader_er_clean_on_re.dataset))

# dataloader_er_backdoor = DataLoader(erased_set_backdoored, batch_size=erasing_size, shuffle=True)


vib, lr = init_vib(args)
vib.to(args.device)

loss_fn = nn.CrossEntropyLoss()

reconstruction_function = nn.MSELoss(size_average=True)

acc_test = []
print("learning")

print('Training VIBI')
print(f'{type(vib.encoder).__name__:>10} encoder params:\t{num_params(vib.encoder) / 1000:.2f} K')
print(f'{type(vib.approximator).__name__:>10} approximator params:\t{num_params(vib.approximator) / 1000:.2f} K')
print(f'{type(vib.decoder).__name__:>10} decoder params:\t{num_params(vib.decoder) / 1000:.2f} K')
# inspect_explanations()


# train VIB
clean_acc_list = []
mse_list = []

train_type = args.train_type

start_time = time.time()
for epoch in range(args.num_epochs):
    vib.train()
    ''' here, we just need to train based on the remaining dataset first, and then prepare the different dataset, normal data similar to the remaining dataset, 
    subset sampled from the remaining dataset, and backdoored samples different from the training dataset '''

    vib, clean_acc_list, mse_list = vib_train(dataloader_remain, vib, loss_fn, reconstruction_function, args, epoch, clean_acc_list,
                                         mse_list, train_loader, train_type, dataloader_er_clean, dataloader_er_with_trigger)

print('acc list',  clean_acc_list)

print('mse list', mse_list)

end_time = time.time()

running_time = end_time - start_time
print(f'VIB Training took {running_time} seconds')

dataloader_erased_with_trigger = DataLoader(erased_set_with_tri, batch_size=args.batch_size, shuffle=True)

vib.eval()

backdoor_acc = eva_vib(vib, dataloader_erased_with_trigger, args, name='on erased with trigger', epoch=999)

acc_r = eva_vib(vib, dataloader_full, args, name='on full training dataset', epoch=999)

acc = eva_vib(vib, test_loader, args, name='on test dataset', epoch=999)

# now the model is trained based on the remaining dataset, it could be treated as a retraining-based unlearned model.
# We collect the gradient at this optimal \theta as the update difference for the data recovery.

start_time = time.time()
temp_grad, temp_img, total_loss_on_re = get_grad_dataset(copy.deepcopy(vib), dataloader_er_clean_on_re, erasing_size)

print("total_loss_on_re", total_loss_on_re/total_loss_on_re, total_loss_on_re)

er_clean_on_re_set = Data.TensorDataset(temp_grad, temp_img)
er_clean_on_re_train_loader = DataLoader(er_clean_on_re_set, batch_size=args.batch_size, shuffle=True)


end_time = time.time()
running_time_grad = end_time - start_time
print(f'grad prepare took {running_time_grad} seconds')



temp_grad, temp_img, total_loss_tri_on_re = get_grad_dataset(copy.deepcopy(vib), dataloader_on_re_with_trigger, erasing_size)
print("total_loss_tri_on_re", total_loss_tri_on_re/total_loss_on_re, total_loss_tri_on_re)
er_on_rem_with_tri_set = Data.TensorDataset(temp_grad, temp_img)
er_on_rem_with_tri_train_loader = DataLoader(er_on_rem_with_tri_set, batch_size=args.batch_size, shuffle=True)


temp_grad, temp_img, total_loss_er_cl = get_grad_dataset(copy.deepcopy(vib), dataloader_er_clean, erasing_size)
print("total_loss_er_cl", total_loss_er_cl/total_loss_on_re, total_loss_er_cl)
er_clean_set = Data.TensorDataset(temp_grad, temp_img)
er_clean_train_loader = DataLoader(er_clean_set, batch_size=args.batch_size, shuffle=True)


temp_grad, temp_img, total_loss_tri_er_cl = get_grad_dataset(copy.deepcopy(vib), dataloader_er_with_trigger, erasing_size)
print("total_loss_tri_er_cl", total_loss_tri_er_cl/total_loss_on_re, total_loss_tri_er_cl)
er_with_trigger_set = Data.TensorDataset(temp_grad, temp_img)
er_with_trigger_train_loader = DataLoader(er_with_trigger_set, batch_size=args.batch_size, shuffle=True)


temp_grad, temp_img, total_loss_remain = get_grad_dataset(copy.deepcopy(vib), dataloader_remain, erasing_size)
print("total_loss_dataloader_remain", total_loss_remain/total_loss_on_re, total_loss_remain)
remaining_grad_set = Data.TensorDataset(temp_grad, temp_img)
remaining_grad_train_loader = DataLoader(remaining_grad_set, batch_size=args.batch_size, shuffle=True)



''' after calculating the update, we finish the full training'''

# Concatenate datasets and create a new loader
#er_trainset = ConcatDataset([erased_on_rem_with_tri,erased_set_with_tri, erasing_set,er_on_remaining_set, erasing_set,er_on_remaining_set, erasing_set,er_on_remaining_set, erasing_set,er_on_remaining_set, erasing_set,er_on_remaining_set, erasing_set,er_on_remaining_set, erasing_set,er_on_remaining_set, erasing_set,er_on_remaining_set])
er_trainset = ConcatDataset([erased_on_rem_with_tri, erased_set_with_tri, erasing_set, er_on_remaining_set])

# remaining dataset for retraining the model
# dataloader_remain = DataLoader(dataset1, batch_size=args.batch_size, shuffle=True)

# if we don't use poisoned set, we use full set
# dataloader_er = DataLoader(er_trainset, batch_size=unlearning_s_size, shuffle=True)


dataloader_er = DataLoader(er_trainset, batch_size=args.batch_size, shuffle=True)

vib_full_trained = copy.deepcopy(vib)

vib_full_trained.decoder.trainable = True
vib_full_trained.fc3.trainable = True


# add erased, full training
start_time = time.time()
for epoch in range(args.num_epochs):
    vib_full_trained.train()
    ''' here, we just need to train based on the remaining dataset first, and then prepare the different dataset, normal data similar to the remaining dataset, 
    subset sampled from the remaining dataset, and backdoored samples different from the training dataset '''

    vib_full_trained, clean_acc_list, mse_list = continue_vib_train(dataloader_er, vib_full_trained, loss_fn, reconstruction_function, args, epoch, clean_acc_list,
                                         mse_list, train_loader, train_type, dataloader_er_clean, dataloader_er_with_trigger)

print('acc list',  clean_acc_list)

print('mse list', mse_list)
end_time = time.time()

running_time = end_time - start_time
print(f'VIB Training took {running_time} seconds')

dataloader_erased_with_trigger = DataLoader(erased_set_with_tri, batch_size=args.batch_size, shuffle=True)

vib_full_trained.eval()

backdoor_acc = eva_vib(vib_full_trained, dataloader_erased_with_trigger, args, name='on erased with trigger', epoch=999)

acc_r = eva_vib(vib_full_trained, dataloader_er, args, name='on full training dataset', epoch=999)

acc = eva_vib(vib_full_trained, test_loader, args, name='on test dataset', epoch=999)





recovery_trainset = ConcatDataset([er_clean_on_re_set, er_clean_set, er_with_trigger_set, er_on_rem_with_tri_set])

recovery_train_loader = DataLoader(recovery_trainset, batch_size=args.batch_size, shuffle=True)

# reconstructor_recover_total = train_reconstructor(recovery_train_loader, reconstruction_function, args)



start_time = time.time()
reconstructor_er_re = train_reconstructor(copy.deepcopy(vib_full_trained), er_clean_on_re_train_loader, reconstruction_function, args)

end_time = time.time()
running_time_recon = end_time - start_time
print(f'reconstruction Training took {running_time_recon} seconds')
print(f'total Training took {running_time_recon + running_time_grad} seconds')


reconstructor_er_on_rem = train_reconstructor(copy.deepcopy(vib_full_trained), er_on_rem_with_tri_train_loader, reconstruction_function, args)

reconstructor_clean = train_reconstructor(copy.deepcopy(vib_full_trained), er_clean_train_loader, reconstruction_function, args)

reconstructor_bac = train_reconstructor(copy.deepcopy(vib_full_trained), er_with_trigger_train_loader, reconstruction_function, args)



avg_mse_on_re, average_sim_on_re, temp_img = get_avg_recon_MSE(copy.deepcopy(reconstructor_er_re),copy.deepcopy(vib_full_trained), er_clean_on_re_train_loader, reconstruction_function, "er_clean_on_re")
total_samples = sum(len(data) for data, _ in er_clean_on_re_train_loader)
y_tensor = torch.ones(total_samples, dtype=torch.long)
er_clean_on_re_veri_set = Data.TensorDataset(temp_img, y_tensor)
print('avg_mse_on_re:', avg_mse_on_re/avg_mse_on_re, avg_mse_on_re, average_sim_on_re)

avg_mse_tri_on_er, average_sim_tri_on_er,temp_img = get_avg_recon_MSE(copy.deepcopy(reconstructor_er_on_rem),copy.deepcopy(vib_full_trained), er_on_rem_with_tri_train_loader, reconstruction_function, "er_with_tri_on_re")
total_samples = sum(len(data) for data, _ in er_on_rem_with_tri_train_loader)
y_tensor = torch.zeros(total_samples, dtype=torch.long)
er_on_rem_with_tri_veri_set = Data.TensorDataset(temp_img, y_tensor)
print('avg_mse_tri_on_er:', avg_mse_tri_on_er/avg_mse_on_re, avg_mse_tri_on_er, average_sim_tri_on_er)

avg_mse_er_cl, average_sim_er_cl,temp_img = get_avg_recon_MSE(copy.deepcopy(reconstructor_clean),copy.deepcopy(vib_full_trained), er_clean_train_loader, reconstruction_function, "er_clean")
total_samples = sum(len(data) for data, _ in er_clean_train_loader)
y_tensor = torch.zeros(total_samples, dtype=torch.long)
er_clean_veri_set = Data.TensorDataset(temp_img, y_tensor)
print('avg_mse_er_cl:', avg_mse_er_cl/avg_mse_on_re, avg_mse_er_cl, average_sim_er_cl)

avg_mse_tri_er_cl, average_sim_tri_er_cl, temp_img = get_avg_recon_MSE(copy.deepcopy(reconstructor_bac),copy.deepcopy(vib_full_trained), er_with_trigger_train_loader, reconstruction_function, "er_with_trigger")
total_samples = sum(len(data) for data, _ in er_with_trigger_train_loader)
y_tensor = torch.zeros(total_samples, dtype=torch.long)
er_with_trigger_veri_set = Data.TensorDataset(temp_img, y_tensor)
print('avg_mse_tri_er_cl:', avg_mse_tri_er_cl/avg_mse_on_re, avg_mse_tri_er_cl, average_sim_tri_er_cl)


avg_mse_remain, average_sim_remain, temp_img = get_avg_recon_MSE(copy.deepcopy(reconstructor_er_on_rem),copy.deepcopy(vib_full_trained), remaining_grad_train_loader, reconstruction_function, "er_with_trigger")
total_samples = sum(len(data) for data, _ in remaining_grad_train_loader)
y_tensor = torch.ones(total_samples, dtype=torch.long)
remaining_grad_veri_set = Data.TensorDataset(temp_img, y_tensor)
print('avg_mse_remain:', avg_mse_remain/avg_mse_on_re, avg_mse_remain, average_sim_remain)


#########


# here, we train the classifier to distinguish the data with and without trigger
classifier_model = LinearModel(n_feature=1 * 28 * 28, n_output=2).to(args.device)



# constructed_verify = prepare_verification_dataset(er_clean_on_re_set, er_on_rem_with_tri_set, er_clean_set, er_with_trigger_set, remaining_grad_set,args)

constructed_verify = ConcatDataset([er_clean_on_re_veri_set, er_on_rem_with_tri_veri_set, er_clean_veri_set, er_with_trigger_veri_set, remaining_grad_veri_set ])

# recovery_train_loader = DataLoader(recovery_trainset, batch_size=args.batch_size, shuffle=True)


dataloader_erased_in_or_not = DataLoader(constructed_verify, batch_size=args.batch_size, shuffle=True)

back_acc_list = []
for epoch in range(args.num_epochs_recon):
    classifier_model.train()
    classifier_model = linear_train(dataloader_erased_in_or_not, vib_full_trained, classifier_model, loss_fn, args)
    backdoor_acc = test_linear_acc(classifier_model, dataloader_erased_in_or_not, args, name='backdoor', epoch=epoch)

# test_acc = test_linear_acc(classifier_model, test_loader, args, name='test')
backdoor_acc = test_linear_acc(classifier_model, dataloader_erased_in_or_not, args, name='backdoor')

acc = infer_linear_from_vib_acc(classifier_model, vib_full_trained, dataloader_er_clean_on_re, args, name='on_re')

acc = infer_linear_from_vib_acc(classifier_model, vib_full_trained, dataloader_on_re_with_trigger, args, name='on_re_with_trigger')


acc = infer_linear_from_vib_acc(classifier_model, vib_full_trained, dataloader_er_clean, args, name='er_clean')

acc = infer_linear_from_vib_acc(classifier_model, vib_full_trained, dataloader_er_with_trigger, args, name='er_with_trigger')

acc = infer_linear_from_vib_acc(classifier_model, vib_full_trained, test_loader, args, name='test_loader')

acc = infer_linear_from_vib_acc(classifier_model, vib_full_trained, dataloader_remain, args, name='remaining_loader')





# first, generate x_hat from trained vae

acc = infer_in_or_not(copy.deepcopy(vib_full_trained), copy.deepcopy(reconstructor_er_re), copy.deepcopy(classifier_model), er_clean_on_re_train_loader)


acc = infer_in_or_not(copy.deepcopy(vib_full_trained), copy.deepcopy(reconstructor_er_on_rem), copy.deepcopy(classifier_model), er_on_rem_with_tri_train_loader)


acc = infer_in_or_not(copy.deepcopy(vib_full_trained), copy.deepcopy(reconstructor_clean), copy.deepcopy(classifier_model), er_clean_train_loader)


acc = infer_in_or_not(copy.deepcopy(vib_full_trained), copy.deepcopy(reconstructor_bac), copy.deepcopy(classifier_model), er_with_trigger_train_loader)


