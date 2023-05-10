import numpy as np
import scipy.linalg as sl


def Identity(d):
    """2nd rank identity tensor of dimension d"""
    return np.eye(d * (d + 1) // 2)


def K():
    A = np.array(
        [
            [2 / 3.0, -1 / 3.0, -1 / 3.0],
            [-1 / 3.0, 2 / 3.0, -1 / 3.0],
            [-1 / 3.0, -1 / 3.0, 2 / 3.0],
        ]
    )
    return sl.block_diag(A, np.eye(3))
