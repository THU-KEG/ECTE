import numpy as np
import random

class ReplayBuffer:
    def __init__(self, num_workers, num_nodes, num_leaves, num_groups):
        self.pool = {}
        self.gold_leaf_indices = {}
        self.K, self.J, self.L = num_workers, num_nodes, num_leaves
        self.num_groups = num_groups

    def add(self, group_id, user_id, node, gold_leaf_node_id=None):
        if group_id not in self.pool:
            self.pool[group_id] = np.zeros([self.K, self.J])
        if gold_leaf_node_id is not None:
            self.gold_leaf_indices[group_id] = gold_leaf_node_id
        self.pool[group_id][user_id][node.node_id] = 1

    def get_log_p(self, group_id):
        if group_id in self.gold_leaf_indices:
            ret = np.zeros(self.L)
            ret[self.gold_leaf_indices[group_id]] = 1
            return np.log(ret)
        else:
            return np.log(np.ones(self.L) / self.L)

    def sample(self, batch_size, group_ids=None):
        # FIXME: is this fast enough?
        if group_ids is not None:
            pool = [self.pool[qid] if qid in self.pool else np.zeros([self.K, self.J]) for qid in group_ids]
            return group_ids, np.stack(pool), np.stack([self.get_log_p(i) for i in group_ids])
        if len(self.pool) < batch_size:
            ids = list(range(self.num_groups))
            random.shuffle(ids)
            # FIXME: maybe duplicate with group_ids if batch_size too large.
            # empty_group_ids = ids[:batch_size-len(group_ids)]
            # pool += [self.pool[qid] if qid in self.pool else np.zeros([self.K, self.J]) for qid in empty_group_ids]
            # group_ids += empty_group_ids
            empty_group_ids = ids[:batch_size]
            pool = [self.pool[qid] if qid in self.pool else np.zeros([self.K, self.J]) for qid in empty_group_ids]
            group_ids = empty_group_ids
            return group_ids, np.stack(pool), np.stack([self.get_log_p(i) for i in group_ids])
        else:
            group_ids = list(self.pool.keys())
            random.shuffle(group_ids)
            group_ids = group_ids[:batch_size]
            return group_ids, np.stack([self.pool[i] for i in group_ids]), np.stack([self.get_log_p(i) for i in group_ids])
