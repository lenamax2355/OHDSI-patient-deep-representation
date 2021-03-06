"""
 Stacked Denoising Autoencoders (SdA)
 References :
   - P. Vincent, H. Larochelle, Y. Bengio, P.A. Manzagol: Extracting and
   Composing Robust Features with Denoising Autoencoders, ICML' 08, 1096-1103,
   2008
   - DeepLearningTutorials
   https://github.com/lisa-lab/DeepLearningTutorials
"""

import sys
import numpy
import csv
from sklearn import preprocessing


numpy.seterr(all='ignore')

def sigmoid(x):
    return 1. / (1 + numpy.exp(-x))

def softmax(x):
    e = numpy.exp(x - numpy.max(x))  # prevent overflow
    if e.ndim == 1:
        return e / numpy.sum(e, axis=0)
    else:  
        return e / numpy.array([numpy.sum(e, axis=1)]).T  # ndim = 2


class SdA(object):
    def __init__(self, input=None, label=None,\
                 n_ins=7840, hidden_layer_sizes=[5000], n_outs=2,\
                 numpy_rng=None):

        self.x = input
        self.y = label

        self.sigmoid_layers = []
        self.dA_layers = []
        self.n_layers = len(hidden_layer_sizes)  # = len(self.rbm_layers)

        if numpy_rng is None:
            numpy_rng = numpy.random.RandomState(1234)


        assert self.n_layers > 0


        # construct multi-layer
        for i in xrange(self.n_layers):
            # layer_size
            if i == 0:
                input_size = n_ins
            else:
                input_size = hidden_layer_sizes[i - 1]

            # layer_input
            if i == 0:
                layer_input = self.x
            else:
                layer_input = self.sigmoid_layers[-1].sample_h_given_v()

            # construct sigmoid_layer
            sigmoid_layer = HiddenLayer(input=layer_input,
                                        n_in=input_size,
                                        n_out=hidden_layer_sizes[i],
                                        numpy_rng=numpy_rng,
                                        activation=sigmoid)
            self.sigmoid_layers.append(sigmoid_layer)


            # construct dA_layers
            dA_layer = dA(input=layer_input,
                          n_visible=input_size,
                          n_hidden=hidden_layer_sizes[i],
                          W=sigmoid_layer.W,
                          hbias=sigmoid_layer.b)
            self.dA_layers.append(dA_layer)


        # layer for output using Logistic Regression
        self.log_layer = LogisticRegression(input=self.sigmoid_layers[-1].sample_h_given_v(),
                                            label=self.y,
                                            n_in=hidden_layer_sizes[-1],
                                            n_out=n_outs)

        # finetune cost: the negative log likelihood of the logistic regression layer
        self.finetune_cost = self.log_layer.negative_log_likelihood()


    def pretrain(self, lr=0.1, corruption_level=0.3, epochs=100):
        for i in xrange(self.n_layers):
            print ("now in layer" + str(i))
            if i == 0:
                layer_input = self.x
            else:
                layer_input = self.sigmoid_layers[i-1].sample_h_given_v(layer_input)

            da = self.dA_layers[i]

            for epoch in xrange(epochs):
                print ("now in epoch" + str(epoch))
                da.train(lr=lr, corruption_level=corruption_level, input=layer_input)

    def finetune(self, lr=0.1, epochs=100):
        layer_input = self.sigmoid_layers[-1].sample_h_given_v()

        # train log_layer
        epoch = 0

        while epoch < epochs:
            print ("now in epoch" + str(epoch))
            self.log_layer.train(lr=lr, input=layer_input)
            # self.finetune_cost = self.log_layer.negative_log_likelihood()
            # print >> sys.stderr, 'Training epoch %d, cost is ' % epoch, self.finetune_cost

            lr *= 0.95
            epoch += 1


    def predict(self, x):
        layer_input = x

        for i in xrange(self.n_layers):
            sigmoid_layer = self.sigmoid_layers[i]
            # rbm_layer = self.rbm_layers[i]
            layer_input = sigmoid_layer.output(input=layer_input)

        out = self.log_layer.predict(layer_input)
        return out


class HiddenLayer(object):
    def __init__(self, input, n_in, n_out,\
                 W=None, b=None, numpy_rng=None, activation=numpy.tanh):

        if numpy_rng is None:
            numpy_rng = numpy.random.RandomState(1234)

        if W is None:
            a = 1. / n_in
            initial_W = numpy.array(numpy_rng.uniform(  # initialize W uniformly
                low=-a,
                high=a,
                size=(n_in, n_out)))

            W = initial_W

        if b is None:
            b = numpy.zeros(n_out)  # initialize bias 0


        self.numpy_rng = numpy_rng
        self.input = input
        self.W = W
        self.b = b

        self.activation = activation

    def output(self, input=None):
        if input is not None:
            self.input = input

        linear_output = numpy.dot(self.input, self.W) + self.b

        return (linear_output if self.activation is None
                else self.activation(linear_output))

    def sample_h_given_v(self, input=None):
        if input is not None:
            self.input = input

        v_mean = self.output()
        h_sample = self.numpy_rng.binomial(size=v_mean.shape,
                                           n=1,
                                           p=v_mean)
        return h_sample


class dA(object):
    def __init__(self, input=None, n_visible=2, n_hidden=3, \
        W=None, hbias=None, vbias=None, numpy_rng=None):

        self.n_visible = n_visible  # num of units in visible (input) layer
        self.n_hidden = n_hidden    # num of units in hidden layer

        if numpy_rng is None:
            numpy_rng = numpy.random.RandomState(1234)

        if W is None:
            a = 1. / n_visible
            initial_W = numpy.array(numpy_rng.uniform(  # initialize W uniformly
                low=-a,
                high=a,
                size=(n_visible, n_hidden)))

            W = initial_W

        if hbias is None:
            hbias = numpy.zeros(n_hidden)  # initialize h bias 0

        if vbias is None:
            vbias = numpy.zeros(n_visible)  # initialize v bias 0

        self.numpy_rng = numpy_rng
        self.x = input
        self.W = W
        self.W_prime = self.W.T
        self.hbias = hbias
        self.vbias = vbias

        # self.params = [self.W, self.hbias, self.vbias]



    def get_corrupted_input(self, input, corruption_level):
        assert corruption_level < 1

        return self.numpy_rng.binomial(size=input.shape,
                                       n=1,
                                       p=1-corruption_level) * input

    # Encode
    def get_hidden_values(self, input):
        return sigmoid(numpy.dot(input, self.W) + self.hbias)

    # Decode
    def get_reconstructed_input(self, hidden):
        return sigmoid(numpy.dot(hidden, self.W_prime) + self.vbias)


    def train(self, lr=0.1, corruption_level=0.3, input=None):
        if input is not None:
            self.x = input

        x = self.x
        tilde_x = self.get_corrupted_input(x, corruption_level)
        y = self.get_hidden_values(tilde_x)
        z = self.get_reconstructed_input(y)

        L_h2 = x - z
        L_h1 = numpy.dot(L_h2, self.W) * y * (1 - y)

        L_vbias = L_h2
        L_hbias = L_h1
        L_W =  numpy.dot(tilde_x.T, L_h1) + numpy.dot(L_h2.T, y)


        self.W += lr * L_W
        self.hbias += lr * numpy.mean(L_hbias, axis=0)
        self.vbias += lr * numpy.mean(L_vbias, axis=0)



    def negative_log_likelihood(self, corruption_level=0.3):
        tilde_x = self.get_corrupted_input(self.x, corruption_level)
        y = self.get_hidden_values(tilde_x)
        z = self.get_reconstructed_input(y)

        cross_entropy = - numpy.mean(
            numpy.sum(self.x * numpy.log(z) +
            (1 - self.x) * numpy.log(1 - z),
                      axis=1))

        return cross_entropy


    def reconstruct(self, x):
        y = self.get_hidden_values(x)
        z = self.get_reconstructed_input(y)
        return z


class LogisticRegression(object):
    def __init__(self, input, label, n_in, n_out):
        self.x = input
        self.y = label
        self.W = numpy.zeros((n_in, n_out))  # initialize W 0
        self.b = numpy.zeros(n_out)          # initialize bias 0

    def train(self, lr=0.1, input=None, L2_reg=0.00):
        if input is not None:
            self.x = input

        p_y_given_x = softmax(numpy.dot(self.x, self.W) + self.b)
        d_y = self.y - p_y_given_x

        self.W += lr * numpy.dot(self.x.T, d_y) - lr * L2_reg * self.W
        self.b += lr * numpy.mean(d_y, axis=0)

    def negative_log_likelihood(self):
        sigmoid_activation = softmax(numpy.dot(self.x, self.W) + self.b)

        cross_entropy = - numpy.mean(
            numpy.sum(self.y * numpy.log(sigmoid_activation) +
            (1 - self.y) * numpy.log(1 - sigmoid_activation),
                      axis=1))

        return cross_entropy

    def predict(self, x):
        return softmax(numpy.dot(x, self.W) + self.b)




def test_SdA(pretrain_lr=0.2, pretraining_epochs=20, corruption_level=0.1, \
             finetune_lr=0.2, finetune_epochs=20):
    split_rule = numpy.load("split_rule.npy")
    result = numpy.load("result_dense.npy")
    #min_max_scaler = preprocessing.MinMaxScaler()
    #result = min_max_scaler.fit_transform(result)
    class_csv = open("classification_final.csv")
    target = []
    reader = csv.reader(class_csv)
    head = next(reader)[2:]
    for line in reader:
        target.append(line[2:])
    target_np = numpy.array(target)
    now_target = (target_np[:,0].astype(int)>0).astype(int)
    sda_target = now_target[split_rule[:6000]]
    sda_target_2 = (sda_target==0).astype(int)
    y = numpy.stack((sda_target, sda_target_2), axis=-1)
    #y = sda_target
    x = result[split_rule[:6000],:]
    rng = numpy.random.RandomState(123)
    print (x.shape)
    print (y.shape)
    # construct SdA
    print ("start construct SdA\n")
    sda = SdA(input=x, label=y, \
              n_ins=1568, hidden_layer_sizes=[10,10], n_outs=2, numpy_rng=rng)
    print ("start construct SdA\n")
    print ("start pre-training\n")
    # pre-training
    sda.pretrain(lr=pretrain_lr, corruption_level=corruption_level, epochs=pretraining_epochs)
    print ("finish pre-training\n")

    print ("start fine-tuning\n")
    # fine-tuning
    sda.finetune(lr=finetune_lr, epochs=finetune_epochs)
    print ("finish fine-tuning\n")

    # test
    print ("start predict\n")
    x = result[split_rule[6000:],:]
    x_result = sda.predict(x)
    print(x_result)
    numpy.save("sda_result.npy",x_result)
    print ("finish predict\n")
if __name__ == "__main__":
    test_SdA()
