import sys, os, time, math, argparse, contextlib
import tensorflow as tf
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import pandas as pd
from matplotlib import offsetbox
from loader import Loader, Loader_cytof_emt
from skimage.io import imsave
from sklearn.manifold import TSNE
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.decomposition import PCA
from scipy.spatial.distance import pdist, squareform
from skimage.io import imsave

import seaborn as sns
sns.set_style('dark')
# sns.set_palette('muted')
# sns.set_context("notebook", font_scale=1.5,
#                 rc={"lines.linewidth": 2.5})

def plot_mnist(args, X, y, X_embedded, name, min_dist=15.):
    fig, ax = plt.subplots(1,1, figsize=(10,10), frameon=False)
    ax.set_xticks([])
    ax.set_yticks([])
    plt.subplots_adjust(left=0.0, bottom=0.0, right=1.0, top=1.0, wspace=0.0, hspace=0.0)
    
    colors = [plt.cm.jet(float(i)/len(np.unique(y))) for i in range(len(np.unique(y)))]
    colors_y = [colors[int(y_)] for y_ in y]
    ax.scatter(X_embedded[:, 0], X_embedded[:, 1], c=colors_y)

    shown_images = np.array([[15., 15.]])
    for i in range(1000):
        for d in range(10):
            if i >= X_embedded[y==d].shape[0]: continue

            dist = np.sum((X_embedded[y==d][i] - shown_images) ** 2, 1)
            if np.min(dist) < min_dist:
                continue
            img = X_embedded[y==d][i]
            shown_images = np.concatenate([shown_images,img.reshape((1,-1))])

            imagebox = offsetbox.AnnotationBbox( 
                offsetbox.OffsetImage(X[y==d][i].reshape(28, 28), cmap=cm.gray_r), X_embedded[y==d][i]
                )
            ax.add_artist(imagebox)
    fig.savefig(args.save_folder+'/embed_w_images'+name)



class SilentFile(object):
    def write(self, x): pass
    def flush(self): pass

@contextlib.contextmanager
def silence():
    save_stdout = sys.stdout
    sys.stdout = SilentFile()
    yield
    sys.stdout = save_stdout

def softmax(x):

    return np.exp(x) / np.sum(np.exp(x), axis=1).reshape((-1,1))

def show_result(args, data, fname, grid_size=(8, 8), grid_pad=5):
    img_height = 28
    img_width = 28
    data = data.reshape((data.shape[0], img_height, img_width))
    img_h, img_w = data.shape[1], data.shape[2]
    grid_h = img_h * grid_size[0] + grid_pad * (grid_size[0] - 1)
    grid_w = img_w * grid_size[1] + grid_pad * (grid_size[1] - 1)
    img_grid = np.zeros((grid_h, grid_w), dtype=np.uint8)
    for i, res in enumerate(data):
        if i >= grid_size[0] * grid_size[1]:
            break
        img = (res) * 255
        img = img.astype(np.uint8)
        row = (i // grid_size[0]) * (img_h + grid_pad)
        col = (i % grid_size[1]) * (img_w + grid_pad)
        img_grid[row:row + img_h, col:col + img_w] = img
    imsave(os.path.join(args.save_folder, fname), img_grid)

def lrelu(x, leak=0.2, name="lrelu"):

  return tf.maximum(x, leak*x)

def get_loader(args, load_full=True):
    if args.data == 'MNIST':
        loader = Loader(args)
    elif args.data == 'cytof_emt':
        loader = Loader_cytof_emt(args)
    elif args.data == 'ZIKA':
        loader = Loader(args, load_full)
    elif args.data == 'FLU':
        loader = Loader(args)
    elif args.data == 'TOY':
        loader = Loader(args)
    else:
        raise Exception("Couldn't parse name of data to use: {}".format(args.data))

    return loader

def tbn(name):

    return tf.get_default_graph().get_tensor_by_name(name)

def obn(name):

    return tf.get_default_graph().get_operation_by_name(name)

def to_one_hot(y, n):
    h = np.zeros((y.shape[0], n))
    h[np.arange(y.shape[0]), y] = 1
    return h

def get_layer(sess, loader, name, test_or_train='test'):
    tensor = tbn(name)
    layer = []
    labels = []
    for batch, batch_labels in loader.iter_batches(test_or_train):
        
        feed = {tbn('x:0'):batch, tbn('is_training:0'):False}
        [act] = sess.run([tensor], feed_dict=feed)

        layer.append(act)
        labels.append(batch_labels)

    layer = np.concatenate(layer, axis=0)
    labels = np.concatenate(labels, axis=0)
    return layer, labels

def plot(args, data, labels, title, fn):
    fig, ax = plt.subplots(1,1)
    ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])

    if data.shape[1]>2:
        return 
        tsne = TSNE(verbose=2)
        data = tsne.fit_transform(data)

    colors = [plt.cm.jet(float(i)/len(np.unique(labels))) for i in range(len(np.unique(labels)))]
    for index,lab in enumerate(np.unique(labels)):
        inds = [True if l==lab else False for l in labels]
        tmp_data = data[inds,:]
        if lab==-1: continue


        # ax.scatter(tmp_data[:,0], tmp_data[:,1], c=colors[int(index)], alpha=.3, s=5, marker='${}$'.format(index), label=int(lab))
        ax.scatter(tmp_data[:,0], tmp_data[:,1], c=colors[int(index)], alpha=.3, s=2)

    # if args.data!='ZIKA':
    #     lgnd = plt.legend(scatterpoints=1, prop={'size':6})
    #     for lh in lgnd.legendHandles:
    #         lh._sizes = [30]
    #         lh.set_alpha(1)

    fig.savefig( os.path.join(args.save_folder,fn), dpi=300)

    plt.close('all')
    print("Plot saved to {}".format(fn))

def activations_heatmap(args, sess, loader, layer, thresh=.5):
    all_acts, all_labels = get_layer(sess, loader, 'layer_encoder_{}_activation:0'.format(layer))

    
    nonzero = all_acts.reshape((-1))[all_acts.reshape((-1)) > 0]

    if layer in args.layers_entropy:
        acts_normalized, labels = get_layer(sess, loader, 'normalized_activations_layer_{}:0'.format(layer))
        normalized_nonzero = acts_normalized.reshape((-1))#[acts_normalized.reshape((-1)) > 0]
        fig, ax = plt.subplots(1,1, figsize=(10,10))
        ax.set_title('ID Regularization')
        ax.set_xlabel('Activation')
        ax.set_ylabel('Log(Count)')

        # ax.hist(np.log(normalized_nonzero), bins=1000)
        # ax.hist(normalized_nonzero, bins=1000)
        n, bins, patches = plt.hist(normalized_nonzero, bins=1000, log=True)
        bin_starts = bins[0:bins.size-1]
        bin_widths = bins[1:bins.size] - bins[0:bins.size-1]
        ax.bar(bin_starts,np.log10(n),bin_widths)
        ax.set_ylim([0,10**6])

        fig.savefig(os.path.join(args.save_folder, 'layer_{}_activations_histogram'.format(layer)))
    else:
        acts_normalized = softmax(all_acts)

        fig, ax = plt.subplots(1,1, figsize=(10,10))
        fn = 'No regularization' if not (args.layers_entropy or args.layers_sparsity) else 'L1 Regularization'
        ax.set_title(fn)
        ax.set_xlabel('Activation')
        ax.set_ylabel('Log(Count)')
        
        # ax.hist(np.log(nonzero), bins=1000)
        # ax.hist(nonzero, bins=1000)

        n, bins, patches = plt.hist(nonzero, bins=1000, log=True)
        bin_starts = bins[0:bins.size-1]
        bin_widths = bins[1:bins.size] - bins[0:bins.size-1]
        ax.bar(bin_starts,np.log10(n),bin_widths)
        ax.set_ylim([0,10**6])

        fig.savefig(os.path.join(args.save_folder, 'layer_{}_activations_histogram'.format(layer)))

    


        


    binarized = acts_normalized
    # binarized = np.where(acts_normalized>thresh, 1, 0)
    fig, axes = plt.subplots(1,10, figsize=(20,5), dpi=150)
    fig.subplots_adjust(hspace=.01, wspace=.02, left=0, right=1, top=1, bottom=.02)
    all_argmaxes = np.zeros((10,10))
    for i in range(10):
        if args.data == 'MNIST':
            # pick out this digit
            all_this_digit = binarized[all_labels==i,:]
        else:
            all_this_digit = binarized[[ii*10+i for ii in range(10)],:]
        
        squaredims = int(math.floor(np.sqrt( args.layers[layer] )))
        this_digit = all_this_digit.mean(axis=0)
        this_digit = this_digit[:squaredims**2].reshape((squaredims,squaredims))
        ax = axes.flatten()[i]
        ax.set_xlabel("{}".format(i), fontsize=14)
        ax.imshow(this_digit, cmap='gray')
        ax.set_xticklabels([])
        ax.set_yticklabels([])
        ax.grid('off')
        ax.set_aspect('equal')
    fig.savefig(os.path.join(args.save_folder, 'layer_{}_activations_heatmap'.format(layer)))
    plt.close('all')
    print("Activations heatmap saved.")
    return





    binarized = acts_normalized
    # binarized = np.where(acts_normalized>thresh, 1, 0)
    fig, axes = plt.subplots(10,10, figsize=(20,20), dpi=150)
    fig.subplots_adjust(hspace=.01, wspace=.02, left=.02, right=1, top=1, bottom=0)
    all_argmaxes = np.zeros((10,10))
    for i in range(10):
        if args.data == 'MNIST':
            # pick out this digit
            all_this_digit = binarized[all_labels==i,:]
        else:
            all_this_digit = binarized[[ii*10+i for ii in range(10)],:]
        axes[i,0].set_ylabel("{}".format(i))
        for j in range(10):
            squaredims = int(math.floor(np.sqrt( args.layers[layer] )))
            this_digit = all_this_digit[j,:squaredims**2].reshape((squaredims,squaredims))
            ax = axes[i,j]
            all_argmaxes[i,j] = this_digit.argmax() 
            ax.imshow(this_digit, cmap='gray')
            ax.set_xticklabels([])
            ax.set_yticklabels([])
            ax.grid('off')
            ax.set_aspect('equal')
    fig.savefig(os.path.join(args.save_folder, 'layer_{}_activations_heatmap'.format(layer)))
    plt.close('all')
    print("Activations heatmap saved.")

def calculate_loss(sess, loader, train_or_test='test'):
    loss_tensor = tbn('loss:0')
    x_tensor = tbn('x:0')
    y_tensor = tbn('y:0')
    losses = []
    for batch, batch_labels in loader.iter_batches(train_or_test):
        feed = {x_tensor:batch,
                y_tensor:batch,
                tbn('is_training:0'):False}
        [l] = sess.run([loss_tensor], feed_dict=feed)
        losses.append(l)

    avg_loss = sum(losses) / float(len(losses))
    return avg_loss

def count_clusters(args, sess, loader, layer, thresh=.5, return_clusters=False, BIN_MIN=10):
    '''Counts the number of clusters after binarizing the activations of the given layer.'''
    acts, labels = get_layer(sess, loader, 'normalized_activations_layer_{}:0'.format(layer))
    unique_argmaxes, unique_argmaxes_counts = np.unique(acts.argmax(axis=1), return_counts=True)
    unique_argmaxes_counts = list(reversed(sorted(unique_argmaxes_counts.tolist())))
    # for i in range(len(unique_argmaxes)):
    #     if i>10: break
    #     print(unique_argmaxes[i], unique_argmaxes_counts[i])
    print("Max neuron values: ", acts.max(axis=1)[:5], "...")
    # print("Number of unique max neurons: ", len(np.unique(acts.argmax(axis=1))))


    binarized = np.where(acts>thresh, 1, 0)

    # k = 10
    # binarized = np.zeros(acts.shape)
    # topk = np.argpartition(acts, -k, axis=1)[:,-k:]
    # for i,row in enumerate(topk):
    #     for j in row:
    #         binarized[i,j] = 1
    unique_rows = np.vstack({tuple(row) for row in binarized})
    num_clusters = unique_rows.shape[0]
    
    num_clusters = 0
    num_excluded = 0
    new_labels = np.zeros(labels.shape)
    for i,row in enumerate(unique_rows):
        rows_equal_to_this_code = np.where(np.all(binarized==row, axis=1))[0]
        if len(rows_equal_to_this_code) < BIN_MIN:
            new_labels[rows_equal_to_this_code] = -1
            num_excluded+=len(rows_equal_to_this_code)
            continue
        new_labels[rows_equal_to_this_code] = num_clusters
        num_clusters+=1
        # labels_code = labels[rows_equal_to_this_code]
        # unique, counts = np.unique(labels_code, return_counts=True)
        # print(np.array([unique,counts]).T)

    print("---- Num clusters: {} ---- Pct clustered: {:.3f} ----".format(num_clusters, 1 - 1.*num_excluded/new_labels.shape[0]))
    acts, _ = get_layer(sess, loader, 'layer_embedding_activation:0')

    
    new_labels_vals, new_labels_counts = np.unique(new_labels, return_counts=True)
    fig, ax = plt.subplots(1,1)
    ax.bar(range(len(new_labels_counts)), new_labels_counts.tolist())#list(reversed(sorted(new_labels_counts.tolist()))))
    ax.set_xlabel('Cluster')
    ax.set_ylabel('Count')
    ax.set_title('Test Set Cluster Counts')
    fig.savefig(os.path.join(args.save_folder, 'cluster_counts'))


    if return_clusters:
        return num_clusters, new_labels 
    return num_clusters     

def calculate_randinds(labels1, labels2):

    return adjusted_rand_score(labels1, labels2)

def calculate_modularity(x, labels, sigma):
    labels = to_one_hot(labels, labels.max()+1)
    pairwise_sq_dists = squareform(pdist(x, 'sqeuclidean'))
    A = np.exp(-pairwise_sq_dists / sigma**2)
    A = A - np.eye(x.shape[0])
    k = A.sum(axis=0)
    M = A.sum()
    B = A - k.reshape((-1,1)).dot(k.reshape((1,-1))) / M
    Q = np.trace(labels.T.dot(B).dot(labels)) / M
    return Q

def calculate_silhouette(x, labels):

    return silhouette_score(x, labels)

def calculate_confusion_matrix(true_labels, clusters):
    true_labels = true_labels[clusters!=-1]
    clusters = clusters[clusters!=-1]

    table = pd.crosstab(true_labels, clusters)

    return table

def decode_cluster_means(args, sess, loader, cluster_labels):
    embedded, labels = get_layer(sess, loader, 'layer_embedding_activation:0', 'test')

    df = pd.DataFrame(embedded)
    df['cluster'] = cluster_labels
    grouped = df.groupby('cluster')
    applied = grouped.apply(lambda x: x.mean())

    e = tbn('ph_embedding:0')
    o = tbn('ph_embedding_decoded:0')

    fig, ax = plt.subplots(1,1)
    all_clusts = []
    del applied['cluster']
    for i,clust in applied.iterrows():
        clust = clust.values.reshape((1,-1))
        [decoded] = sess.run([o], feed_dict={e:clust, tbn('is_training:0'):False})
        all_clusts.append(decoded.reshape((1,-1)))

    all_clusts = np.concatenate(all_clusts, axis=0)
    g = math.ceil(math.sqrt(all_clusts.shape[0]))
    # all_clusts = all_clusts[:,:g**2]
    print(all_clusts.shape)

    show_result(args, all_clusts, 'cluster_means_decoded.png', grid_size=(g,g))

def confusion_matrix(args, sess, loader, layer, clusters):
    input_layer, labels = get_layer(sess, loader, 'x:0')


    table = calculate_confusion_matrix(labels, clusters)
    table = table / table.sum(axis=0)
    # table = table.transpose()
    # table['amax'] = table.idxmax(axis=1)
    # table = table.sort_values('amax')
    # del table['amax']
    # table = table.transpose()
    fig, ax = plt.subplots(1,1)
    ax.imshow(table.as_matrix(), cmap='jet')
    fig.savefig(args.save_folder + '/confusion_matrix_{}.png'.format(layer))

