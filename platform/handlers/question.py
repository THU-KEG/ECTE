from handlers import main_handler
from .tax_node import TaxNode
import time
import numpy as np
import sqlite3
import io
import copy
import torch


class Question:
    def __init__(self, question_id, answers, concept, gold_answer):
        self.question_id = question_id
        self.answers = answers
        self.concept = concept
        self.given_time = 0
        self.gold_answer = gold_answer
        self.is_task_valid = True

    def to_array(self, K, J):
        ret = torch.zeros(K, J)
        for user_id, node in self.answers.items():
            ret[user_id][node.node_id] = 1
        return ret

    def can_return(self):
        return time.time() - self.given_time > main_handler.business_config["timeout_threshold"] and self.is_task_valid

    def copy(self):
        ret = copy.copy(self)
        ret.prob = copy.copy(ret.prob)
        return ret

    def calculate_estimation_quality(self):
        specify_vec = np.array([answer.specificity for answer in self.answers.values()])
        relation_matrix = np.array(
            [[TaxNode.has_hyper_or_hypo_relationship(answer_i, answer_j) for answer_j in self.answers.values()]
             for answer_i in self.answers.values()])
        self.estimation_quality = specify_vec.T @ relation_matrix @ specify_vec

