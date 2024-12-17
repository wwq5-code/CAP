

import numpy as np
import matplotlib.pyplot as plt

epsilon = 3
beta = 1 / epsilon


x=[1, 2, 3, 4, 5 ]
# validation_for_plt =[97,95.8600, 94.9400, 93.5400, 93.2400]
# attack_for_plt=[0, 0.3524, 0, 0.1762, 0.1762]
# basic_for_plt=[99.8, 99.8, 99.8, 99.8, 99.8]

labels = ['0.5', '0.6', '0.7', '0.8', '0.9']
# unl_org = [97.77, 97.55, 97.35, 97.29, 97.21, 97.21]

unl_cap = [1,1, 1, 1, 1 ]

unl_mib = [0.9173, 0.9289, 0.9314, 0.9482, 0.9521 ]



plt.style.use('seaborn')
plt.figure(figsize=(5.5, 5.3))
l_w=5
m_s=15
marker_s = 3
markevery=1
#plt.figure(figsize=(8, 5.3))
#plt.plot(x, unl_fr, color='blue', marker='^', label='Retrain',linewidth=l_w, markersize=m_s)
plt.plot(x, unl_cap, linestyle='-', color='#797BB7', marker='o', fillstyle='full', markevery=markevery,label='EUV', linewidth=l_w, markersize=m_s, markeredgewidth=marker_s)


#plt.plot(x, unl_muv, linestyle='--', color='#9BC985',  marker='s', fillstyle='full', markevery=markevery, label='TaPD',linewidth=l_w, markersize=m_s, markeredgewidth=marker_s)


# plt.plot(x, unl_mib_bck, linestyle=':', color='r',  marker='^', fillstyle='none', markevery=markevery,
#          label='MIB (bac.)', linewidth=l_w,  markersize=m_s, markeredgewidth=marker_s)


plt.plot(x, unl_mib, linestyle='-.', color='#2A5522',  marker='D', fillstyle='full', markevery=markevery,
         label='MIB',linewidth=l_w, markersize=m_s, markeredgewidth=marker_s)



#plt.plot(x, unl_vibu, color='silver',  marker='d',  label='VIBU',linewidth=4,  markersize=10)

# plt.plot(x, y_sa03, color='r',  marker='2',  label='AAAI21 A_acc, pr=0.3',linewidth=3, markersize=8)
# plt.plot(x, y_sa05, color='darkblue',  marker='4',  label='AAAI21 A_acc, pr=0.5',linewidth=3, markersize=8)
# plt.plot(x, y_ma03, color='darkviolet',  marker='3',  label='FedMC A_acc, pr=0.3',linewidth=3, markersize=8)
# plt.plot(x, y_ma05, color='cyan',  marker='p',  label='FedMC A_acc, pr=0.5',linewidth=3, markersize=8)


# plt.grid()
leg = plt.legend(fancybox=True, shadow=True)
# plt.xlabel('Malicious Client Ratio (%)' ,fontsize=16)
plt.ylabel('Verifiability' ,fontsize=28)
my_y_ticks = np.arange(0.9, 1.01, 0.02)
plt.yticks(my_y_ticks,fontsize=28)
plt.ylim(0.9, 1.01)
plt.xlabel('$\it{ESR}$ (%)', fontsize=28)

plt.xticks(x, labels, fontsize=28)
# plt.title('CIFAR10 IID')

#plt.annotate(r"1e0", xy=(0.1, 1.01), xycoords='axes fraction', xytext=(-10, 10),textcoords='offset points', ha='right', va='center', fontsize=15)


# plt.title('(c) Utility Preservation', fontsize=24)
plt.legend(loc=(0.01, 0.4),fontsize=28)
plt.tight_layout()
#plt.title("MNIST")
plt.rcParams['figure.figsize'] = (2.0, 1)
plt.rcParams['image.interpolation'] = 'nearest'
plt.rcParams['figure.subplot.left'] = 0.11
plt.rcParams['figure.subplot.bottom'] = 0.08
plt.rcParams['figure.subplot.right'] = 0.977
plt.rcParams['figure.subplot.top'] = 0.969
plt.savefig('celeba_verifiability_sample_size_sim_analysis.pdf', format='pdf', dpi=200)
plt.show()