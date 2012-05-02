import numpy as np
from scipy.stats import norm

# d-prime
def dprime(confusion_matrix):
    """
    Function takes in a 2x2 confusion matrix and returns the d-prime value for the predictions.
    
    d' = z(hit rate)-z(false alarm rate)
    
    http://en.wikipedia.org/wiki/D'
    """
    if max(confusion_matrix.shape) > 2:
        return False 
    else:
        hit_rate = confusion_matrix[0, 0] / confusion_matrix[0, :].sum()
        fa_rate = confusion_matrix[1, 0] / confusion_matrix[1, :].sum()

        nudge = 0.0001
        if (hit_rate >= 1): hit_rate = 1 - nudge
        if (hit_rate <= 0): hit_rate = 0 + nudge
        if (fa_rate >= 1): fa_rate = 1 - nudge
        if (fa_rate <= 0): fa_rate = 0 + nudge
        
        dp = norm.ppf(hit_rate)-norm.ppf(fa_rate)
        return dp

# accuracy (% correct)
def acc(confusion_matrix):
    """Function takes in a 1-D array of expected values and a 1-D array of predictions
    and returns the fraction of correct predictions"""
    a = confusion_matrix.diagonal().sum() / confusion_matrix.sum()
    return a

# matthew's correlation coefficient
def mcc(confusion_matrix):
    """Function takes in a 1-D array of expected values and a 1-D array of predictions
    and returns the Matthew's Correlation Coefficient for the predictions.
    
    MCC = (TP*TN-FP*FN)/sqrt((TP+FP)*(TP+FN)*(TN+FP)*(TN+FN))
    
    http://en.wikipedia.org/wiki/Matthews_correlation_coefficient

    """
    if max(confusion_matrix.shape) > 2:
        return False 
    else:
        true_pos = confusion_matrix[0, 0]
        true_neg = confusion_matrix[1, 1]
        false_pos = confusion_matrix[1, 0]
        false_neg = confusion_matrix[0, 1]
        a = (true_pos*true_neg-false_pos*false_neg)/np.sqrt((true_pos+false_pos)*(true_pos+false_neg)*(true_neg+false_pos)*(true_neg+false_neg))
        return a

        # create a confusion matrix
def create_conf_matrix(expected, predicted):
    """
    Function takes in a 1-D array of expected values and a 1-D array of predictions
    and returns a confusion matrix with size corresponding to the number of classes.
    
    http://en.wikipedia.org/wiki/Confusion_matrix

    Keyword arguments:
    expected  -- list of expected or true values
    predicted -- list of predicted or response values

    Returns the confusion matrix as a numpy array m[expectation,prediction]
    
    """
    n_classes = max(len(set(expected)), len(set(predicted)))

    m = np.zeros((n_classes, n_classes))
    for exp, pred in zip(expected, predicted):
        m[exp,pred] += 1
    return m

class ConfusionMatrix:
    def __init__(self, expected, predicted):
        self.matrix = create_conf_matrix(expected, predicted)
    def size(self):
        return max(self.matrix.shape)
    def dprime(self):
        return dprime(self.matrix)
    def acc(self):
        return acc(self.matrix)
    def mcc(self):
        return mcc(self.matrix)
