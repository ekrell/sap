# Copyright 2000-2009 by Iddo Friedberg.  All rights reserved.
# This code is part of the Biopython distribution and governed by its
# license.  Please see the LICENSE file that should have been included
# as part of this package.
#
# Iddo Friedberg idoerg@cc.huji.ac.il

"""Substitution matrices, log odds matrices, and operations on them.

General:
-------

This module provides a class and a few routines for generating
substitution matrices, similar ot BLOSUM or PAM matrices, but based on
user-provided data.
The class used for these matrices is SeqMat

Matrices are implemented as a dictionary. Each index contains a 2-tuple,
which are the two residue/nucleotide types replaced. The value differs
according to the matrix's purpose: e.g in a log-odds frequency matrix, the
value would be log(Pij/(Pi*Pj)) where:
Pij: frequency of substitution of letter (residue/nucleotide) i by j
Pi, Pj: expected frequencies of i and j, respectively.

Usage:
-----
The following section is laid out in the order by which most people wish
to generate a log-odds matrix. Of course, interim matrices can be
generated and investigated. Most people just want a log-odds matrix,
that's all.

Generating an Accepted Replacement Matrix:
-----------------------------------------
Initially, you should generate an accepted replacement matrix (ARM)
from your data. The values in ARM are the _counted_ number of
replacements according to your data. The data could be a set of pairs
or multiple alignments. So for instance if Alanine was replaced by
Cysteine 10 times, and Cysteine by Alanine 12 times, the corresponding
ARM entries would be:
['A','C']: 10,
['C','A'] 12
As order doesn't matter, user can already provide only one entry:
['A','C']: 22
A SeqMat instance may be initialized with either a full (first
method of counting: 10, 12) or half (the latter method, 22) matrix. A
Full protein alphabet matrix would be of the size 20x20 = 400. A Half
matrix of that alphabet would be 20x20/2 + 20/2 = 210. That is because
same-letter entries don't change. (The matrix diagonal). Given an
alphabet size of N:
Full matrix size:N*N
Half matrix size: N(N+1)/2

If you provide a full matrix, the constructor will create a half-matrix
automatically.
If you provide a half-matrix, make sure of a (low, high) sorted order in
the keys: there should only be
a ('A','C') not a ('C','A').

Internal functions:

Generating the observed frequency matrix (OFM):
----------------------------------------------
Use: OFM = _build_obs_freq_mat(ARM)
The OFM is generated from the ARM, only instead of replacement counts, it
contains replacement frequencies.

Generating an expected frequency matrix (EFM):
---------------------------------------------
Use: EFM = _build_exp_freq_mat(OFM,exp_freq_table)
exp_freq_table: should be a freqTableC instantiation. See freqTable.py for
detailed information. Briefly, the expected frequency table has the
frequencies of appearance for each member of the alphabet

Generating a substitution frequency matrix (SFM):
------------------------------------------------
Use: SFM = _build_subs_mat(OFM,EFM)
Accepts an OFM, EFM. Provides the division product of the corresponding
values.

Generating a log-odds matrix (LOM):
----------------------------------
Use: LOM=_build_log_odds_mat(SFM[,logbase=10,factor=10.0,roundit=1])
Accepts an SFM. logbase: base of the logarithm used to generate the
log-odds values. factor: factor used to multiply the log-odds values.
roundit: default - true. Whether to round the values.
Each entry is generated by log(LOM[key])*factor
And rounded if required.

External:
---------
In most cases, users will want to generate a log-odds matrix only, without
explicitly calling the OFM --> EFM --> SFM stages. The function
build_log_odds_matrix does that. User provides an ARM and an expected
frequency table. The function returns the log-odds matrix.

Methods for subtraction, addition and multiplication of matrices:
-----------------------------------------------------------------
* Generation of an expected frequency table from an observed frequency
  matrix.
* Calculation of linear correlation coefficient between two matrices.
* Calculation of relative entropy is now done using the
  _make_relative_entropy method and is stored in the member
  self.relative_entropy
* Calculation of entropy is now done using the _make_entropy method and
  is stored in the member self.entropy.
* Jensen-Shannon distance between the distributions from which the
  matrices are derived. This is a distance function based on the
  distribution's entropies.
"""


import re
import sys
import copy
import math
import warnings

# BioPython imports
import Bio
from SAP.Bio import Alphabet
from SAP.Bio.SubsMat import FreqTable

log = math.log
# Matrix types
NOTYPE = 0
ACCREP = 1
OBSFREQ = 2
SUBS = 3
EXPFREQ = 4
LO = 5
EPSILON = 0.00000000000001


class SeqMat(dict):
    """A Generic sequence matrix class
    The key is a 2-tuple containing the letter indices of the matrix. Those
    should be sorted in the tuple (low, high). Because each matrix is dealt
    with as a half-matrix."""

    def _alphabet_from_matrix(self):
        ab_dict = {}
        s = ''
        for i in self:
            ab_dict[i[0]] = 1
            ab_dict[i[1]] = 1
        for i in sorted(ab_dict):
            s += i
        self.alphabet.letters = s

    def __init__(self, data=None, alphabet=None, mat_name='', build_later=0):
        # User may supply:
        # data: matrix itself
        # mat_name: its name. See below.
        # alphabet: an instance of Bio.Alphabet, or a subclass. If not
        # supplied, constructor builds its own from that matrix.
        # build_later: skip the matrix size assertion. User will build the
        # matrix after creating the instance. Constructor builds a half matrix
        # filled with zeroes.

        assert isinstance(mat_name, str)

        # "data" may be:
        # 1) None --> then self.data is an empty dictionary
        # 2) type({}) --> then self takes the items in data
        # 3) An instance of SeqMat
        # This whole creation-during-execution is done to avoid changing
        # default values, the way Python does because default values are
        # created when the function is defined, not when it is created.
        if data:
            try:
                self.update(data)
            except ValueError:
                raise ValueError("Failed to store data in a dictionary")
        if alphabet is None:
            alphabet = Alphabet.Alphabet()
        assert Alphabet.generic_alphabet.contains(alphabet)
        self.alphabet = alphabet

        # If passed alphabet is empty, use the letters in the matrix itself
        if not self.alphabet.letters:
            self._alphabet_from_matrix()
        # Assert matrix size: half or full
        if not build_later:
            N = len(self.alphabet.letters)
            assert len(self) == N**2 or len(self) == N*(N+1)/2
        self.ab_list = list(self.alphabet.letters)
        self.ab_list.sort()
        # Names: a string like "BLOSUM62" or "PAM250"
        self.mat_name = mat_name
        if build_later:
            self._init_zero()
        else:
            # Convert full to half
            self._full_to_half()
            self._correct_matrix()
        self.sum_letters = {}
        self.relative_entropy = 0

    def _correct_matrix(self):
        keylist = self.keys()
        for key in keylist:
            if key[0] > key[1]:
                self[(key[1], key[0])] = self[key]
                del self[key]

    def _full_to_half(self):
        """
        Convert a full-matrix to a half-matrix
        """
        # For instance: two entries ('A','C'):13 and ('C','A'):20 will be summed
        # into ('A','C'): 33 and the index ('C','A') will be deleted
        # alphabet.letters:('A','A') and ('C','C') will remain the same.

        N = len(self.alphabet.letters)
        # Do nothing if this is already a half-matrix
        if len(self) == N*(N+1)/2:
            return
        for i in self.ab_list:
            for j in self.ab_list[:self.ab_list.index(i)+1]:
                if i != j:
                    self[j, i] = self[j, i] + self[i, j]
                    del self[i, j]

    def _init_zero(self):
        for i in self.ab_list:
            for j in self.ab_list[:self.ab_list.index(i)+1]:
                self[j, i] = 0.

    def make_entropy(self):
        self.entropy = 0
        for i in self:
            if self[i] > EPSILON:
                self.entropy += self[i]*log(self[i])/log(2)
        self.entropy = -self.entropy

    def sum(self):
        result = {}
        for letter in self.alphabet.letters:
            result[letter] = 0.0
        for pair, value in self.iteritems():
            i1, i2 = pair
            if i1 == i2:
                result[i1] += value
            else:
                result[i1] += value / 2
                result[i2] += value / 2
        return result

    def print_full_mat(self, f=None, format="%4d", topformat="%4s",
                alphabet=None, factor=1, non_sym=None):
        f = f or sys.stdout
        # create a temporary dictionary, which holds the full matrix for
        # printing
        assert non_sym is None or isinstance(non_sym, float) or \
        isinstance(non_sym, int)
        full_mat = copy.copy(self)
        for i in self:
            if i[0] != i[1]:
                full_mat[(i[1], i[0])] = full_mat[i]
        if not alphabet:
            alphabet = self.ab_list
        topline = ''
        for i in alphabet:
            topline = topline + topformat % i
        topline = topline + '\n'
        f.write(topline)
        for i in alphabet:
            outline = i
            for j in alphabet:
                if alphabet.index(j) > alphabet.index(i) and non_sym is not None:
                    val = non_sym
                else:
                    val = full_mat[i, j]
                    val *= factor
                if val <= -999:
                    cur_str = '  ND'
                else:
                    cur_str = format % val

                outline = outline+cur_str
            outline = outline + '\n'
            f.write(outline)

    def print_mat(self, f=None, format="%4d", bottomformat="%4s",
                alphabet=None, factor=1):
        """Print a nice half-matrix. f=sys.stdout to see on the screen
        User may pass own alphabet, which should contain all letters in the
        alphabet of the matrix, but may be in a different order. This
        order will be the order of the letters on the axes"""

        f = f or sys.stdout
        if not alphabet:
            alphabet = self.ab_list
        bottomline = ''
        for i in alphabet:
            bottomline = bottomline + bottomformat % i
        bottomline = bottomline + '\n'
        for i in alphabet:
            outline = i
            for j in alphabet[:alphabet.index(i)+1]:
                try:
                    val = self[j, i]
                except KeyError:
                    val = self[i, j]
                val *= factor
                if val == -999:
                    cur_str = '  ND'
                else:
                    cur_str = format % val

                outline = outline + cur_str
            outline = outline + '\n'
            f.write(outline)
        f.write(bottomline)

    def __str__(self):
        """Print a nice half-matrix."""
        output = ""
        alphabet = self.ab_list
        n = len(alphabet)
        for i in range(n):
            c1 = alphabet[i]
            output += c1
            for j in range(i+1):
                c2 = alphabet[j]
                try:
                    val = self[c2, c1]
                except KeyError:
                    val = self[c1, c2]
                if val == -999:
                    output += '  ND'
                else:
                    output += "%4d" % val
            output += '\n'
        output += '%4s' * n % tuple(alphabet) + "\n"
        return output

    def __sub__(self, other):
        """ returns a number which is the subtraction product of the two matrices"""
        mat_diff = 0
        for i in self:
            mat_diff += (self[i] - other[i])
        return mat_diff

    def __mul__(self, other):
        """ returns a matrix for which each entry is the multiplication product of the
        two matrices passed"""
        new_mat = copy.copy(self)
        for i in self:
            new_mat[i] *= other[i]
        return new_mat

    def __add__(self, other):
        new_mat = copy.copy(self)
        for i in self:
            new_mat[i] += other[i]
        return new_mat


class AcceptedReplacementsMatrix(SeqMat):
    """Accepted replacements matrix"""


class ObservedFrequencyMatrix(SeqMat):
    """Observed frequency matrix"""


class ExpectedFrequencyMatrix(SeqMat):
    """Expected frequency matrix"""


class SubstitutionMatrix(SeqMat):
    """Substitution matrix"""

    def calculate_relative_entropy(self, obs_freq_mat):
        """Calculate and return the relative entropy with respect to an
        observed frequency matrix"""
        relative_entropy = 0.
        for key, value in self.iteritems():
            if value > EPSILON:
                relative_entropy += obs_freq_mat[key] * log(value)
        relative_entropy /= log(2)
        return relative_entropy


class LogOddsMatrix(SeqMat):
    """Log odds matrix"""

    def calculate_relative_entropy(self, obs_freq_mat):
        """Calculate and return the relative entropy with respect to an
        observed frequency matrix"""
        relative_entropy = 0.
        for key, value in self.iteritems():
            relative_entropy += obs_freq_mat[key] * value / log(2)
        return relative_entropy


def _build_obs_freq_mat(acc_rep_mat):
    """
    build_obs_freq_mat(acc_rep_mat):
    Build the observed frequency matrix, from an accepted replacements matrix
    The acc_rep_mat matrix should be generated by the user.
    """
    # Note: acc_rep_mat should already be a half_matrix!!
    total = float(sum(acc_rep_mat.values()))
    obs_freq_mat = ObservedFrequencyMatrix(alphabet=acc_rep_mat.alphabet,
                                           build_later=1)
    for i in acc_rep_mat:
        obs_freq_mat[i] = acc_rep_mat[i] / total
    return obs_freq_mat


def _exp_freq_table_from_obs_freq(obs_freq_mat):
    exp_freq_table = {}
    for i in obs_freq_mat.alphabet.letters:
        exp_freq_table[i] = 0.
    for i in obs_freq_mat:
        if i[0] == i[1]:
            exp_freq_table[i[0]] += obs_freq_mat[i]
        else:
            exp_freq_table[i[0]] += obs_freq_mat[i] / 2.
            exp_freq_table[i[1]] += obs_freq_mat[i] / 2.
    return FreqTable.FreqTable(exp_freq_table, FreqTable.FREQ)


def _build_exp_freq_mat(exp_freq_table):
    """Build an expected frequency matrix
    exp_freq_table: should be a FreqTable instance
    """
    exp_freq_mat = ExpectedFrequencyMatrix(alphabet=exp_freq_table.alphabet,
                                          build_later=1)
    for i in exp_freq_mat:
        if i[0] == i[1]:
            exp_freq_mat[i] = exp_freq_table[i[0]]**2
        else:
            exp_freq_mat[i] = 2.0*exp_freq_table[i[0]]*exp_freq_table[i[1]]
    return exp_freq_mat


#
# Build the substitution matrix
#
def _build_subs_mat(obs_freq_mat, exp_freq_mat):
    """ Build the substitution matrix """
    if obs_freq_mat.ab_list != exp_freq_mat.ab_list:
        raise ValueError("Alphabet mismatch in passed matrices")
    subs_mat = SubstitutionMatrix(obs_freq_mat)
    for i in obs_freq_mat:
        subs_mat[i] = obs_freq_mat[i]/exp_freq_mat[i]
    return subs_mat


#
# Build a log-odds matrix
#
def _build_log_odds_mat(subs_mat, logbase=2, factor=10.0, round_digit=0, keep_nd=0):
    """_build_log_odds_mat(subs_mat,logbase=10,factor=10.0,round_digit=1):
    Build a log-odds matrix
    logbase=2: base of logarithm used to build (default 2)
    factor=10.: a factor by which each matrix entry is multiplied
    round_digit: roundoff place after decimal point
    keep_nd: if true, keeps the -999 value for non-determined values (for which there
    are no substitutions in the frequency substitutions matrix). If false, plants the
    minimum log-odds value of the matrix in entries containing -999
    """
    lo_mat = LogOddsMatrix(subs_mat)
    for key, value in subs_mat.iteritems():
        if value < EPSILON:
            lo_mat[key] = -999
        else:
            lo_mat[key] = round(factor*log(value)/log(logbase), round_digit)
    mat_min = min(lo_mat.values())
    if not keep_nd:
        for i in lo_mat:
            if lo_mat[i] <= -999:
                lo_mat[i] = mat_min
    return lo_mat


#
# External function. User provides an accepted replacement matrix, and,
# optionally the following: expected frequency table, log base, mult. factor,
# and rounding factor. Generates a log-odds matrix, calling internal SubsMat
# functions.
#
def make_log_odds_matrix(acc_rep_mat, exp_freq_table=None, logbase=2,
                         factor=1., round_digit=9, keep_nd=0):
    obs_freq_mat = _build_obs_freq_mat(acc_rep_mat)
    if not exp_freq_table:
        exp_freq_table = _exp_freq_table_from_obs_freq(obs_freq_mat)
    exp_freq_mat = _build_exp_freq_mat(exp_freq_table)
    subs_mat = _build_subs_mat(obs_freq_mat, exp_freq_mat)
    lo_mat = _build_log_odds_mat(subs_mat, logbase, factor, round_digit, keep_nd)
    return lo_mat


def observed_frequency_to_substitution_matrix(obs_freq_mat):
    exp_freq_table = _exp_freq_table_from_obs_freq(obs_freq_mat)
    exp_freq_mat = _build_exp_freq_mat(exp_freq_table)
    subs_mat = _build_subs_mat(obs_freq_mat, exp_freq_mat)
    return subs_mat


def read_text_matrix(data_file):
    matrix = {}
    tmp = data_file.read().split("\n")
    table=[]
    for i in tmp:
        table.append(i.split())
    # remove records beginning with ``#''
    for rec in table[:]:
        if (rec.count('#') > 0):
            table.remove(rec)

    # remove null lists
    while (table.count([]) > 0):
        table.remove([])
    # build a dictionary
    alphabet = table[0]
    j = 0
    for rec in table[1:]:
        # print j
        row = alphabet[j]
        # row = rec[0]
        if re.compile('[A-z\*]').match(rec[0]):
            first_col = 1
        else:
            first_col = 0
        i = 0
        for field in rec[first_col:]:
            col = alphabet[i]
            matrix[(row, col)] = float(field)
            i += 1
        j += 1
    # delete entries with an asterisk
    for i in matrix.keys():
        if '*' in i:
            del(matrix[i])
    ret_mat = SeqMat(matrix)
    return ret_mat

diagNO = 1
diagONLY = 2
diagALL = 3


def two_mat_relative_entropy(mat_1, mat_2, logbase=2, diag=diagALL):
    rel_ent = 0.
    key_list_1 = sorted(mat_1)
    key_list_2 = sorted(mat_2)
    key_list = []
    sum_ent_1 = 0.
    sum_ent_2 = 0.
    for i in key_list_1:
        if i in key_list_2:
            key_list.append(i)
    if len(key_list_1) != len(key_list_2):
        sys.stderr.write("Warning: first matrix has more entries than the second\n")
    if key_list_1 != key_list_2:
        sys.stderr.write("Warning: indices not the same between matrices\n")
    for key in key_list:
        if diag == diagNO and key[0] == key[1]:
            continue
        if diag == diagONLY and key[0] != key[1]:
            continue
        if mat_1[key] > EPSILON and mat_2[key] > EPSILON:
            sum_ent_1 += mat_1[key]
            sum_ent_2 += mat_2[key]

    for key in key_list:
        if diag == diagNO and key[0] == key[1]:
            continue
        if diag == diagONLY and key[0] != key[1]:
            continue
        if mat_1[key] > EPSILON and mat_2[key] > EPSILON:
            val_1 = mat_1[key] / sum_ent_1
            val_2 = mat_2[key] / sum_ent_2
#            rel_ent += mat_1[key] * log(mat_1[key]/mat_2[key])/log(logbase)
            rel_ent += val_1 * log(val_1/val_2)/log(logbase)
    return rel_ent


## Gives the linear correlation coefficient between two matrices
def two_mat_correlation(mat_1, mat_2):
    try:
        import numpy
    except ImportError:
        raise ImportError("Please install Numerical Python (numpy) if you want to use this function")
    values = []
    assert mat_1.ab_list == mat_2.ab_list
    for ab_pair in mat_1:
        try:
            values.append((mat_1[ab_pair], mat_2[ab_pair]))
        except KeyError:
            raise ValueError("%s is not a common key" % ab_pair)
    correlation_matrix = numpy.corrcoef(values, rowvar=0)
    correlation = correlation_matrix[0, 1]
    return correlation


# Jensen-Shannon Distance
# Need to input observed frequency matrices
def two_mat_DJS(mat_1, mat_2, pi_1=0.5, pi_2=0.5):
    assert mat_1.ab_list == mat_2.ab_list
    assert pi_1 > 0 and pi_2 > 0 and pi_1< 1 and pi_2 <1
    assert not (pi_1 + pi_2 - 1.0 > EPSILON)
    sum_mat = SeqMat(build_later=1)
    sum_mat.ab_list = mat_1.ab_list
    for i in mat_1:
        sum_mat[i] = pi_1 * mat_1[i] + pi_2 * mat_2[i]
    sum_mat.make_entropy()
    mat_1.make_entropy()
    mat_2.make_entropy()
    # print mat_1.entropy, mat_2.entropy
    dJS = sum_mat.entropy - pi_1 * mat_1.entropy - pi_2 * mat_2.entropy
    return dJS

"""
This isn't working yet. Boo hoo!
def two_mat_print(mat_1, mat_2, f=None, alphabet=None, factor_1=1, factor_2=1,
                  format="%4d", bottomformat="%4s", topformat="%4s",
                  topindent=7*" ", bottomindent=1*" "):
    f = f or sys.stdout
    if not alphabet:
        assert mat_1.ab_list == mat_2.ab_list
        alphabet = mat_1.ab_list
    len_alphabet = len(alphabet)
    print_mat = {}
    topline = topindent
    bottomline = bottomindent
    for i in alphabet:
        bottomline += bottomformat % i
        topline += topformat % alphabet[len_alphabet-alphabet.index(i)-1]
    topline += '\n'
    bottomline += '\n'
    f.write(topline)
    for i in alphabet:
        for j in alphabet:
            print_mat[i, j] = -999
    diag_1 = {}
    diag_2 = {}
    for i in alphabet:
        for j in alphabet[:alphabet.index(i)+1]:
            if i == j:
                diag_1[i] = mat_1[(i, i)]
                diag_2[i] = mat_2[(alphabet[len_alphabet-alphabet.index(i)-1],
                    alphabet[len_alphabet-alphabet.index(i)-1])]
            else:
                if i > j:
                    key = (j, i)
                else:
                    key = (i, j)
                mat_2_key = [alphabet[len_alphabet-alphabet.index(key[0])-1],
                    alphabet[len_alphabet-alphabet.index(key[1])-1]]
                # print mat_2_key
                mat_2_key.sort()
                mat_2_key = tuple(mat_2_key)
                # print key, "||",  mat_2_key
                print_mat[key] = mat_2[mat_2_key]
                print_mat[(key[1], key[0])] = mat_1[key]
    for i in alphabet:
        outline = i
        for j in alphabet:
            if i == j:
                if diag_1[i] == -999:
                    val_1 = ' ND'
                else:
                    val_1 = format % (diag_1[i]*factor_1)
                if diag_2[i] == -999:
                    val_2 = ' ND'
                else:
                    val_2 = format % (diag_2[i]*factor_2)
                cur_str = val_1 + "  " + val_2
            else:
                if print_mat[(i, j)] == -999:
                    val = ' ND'
                elif alphabet.index(i) > alphabet.index(j):
                    val = format % (print_mat[(i, j)]*factor_1)
                else:
                    val = format % (print_mat[(i, j)]*factor_2)
                cur_str = val
            outline += cur_str
        outline += bottomformat % (alphabet[len_alphabet-alphabet.index(i)-1] +
                                 '\n')
        f.write(outline)
    f.write(bottomline)
"""
