import torch
from torch import nn
from torch.nn import functional as F
from handlers import main_handler

def distance(node1, node2):
    ''' distance based on path name string.
        >>> class Node: pass
        >>> node1, node2 = Node(), Node()
        >>> node1.name = "A/B/C"
        >>> node2.name = "A/D/E/F"
        >>> distance(node1, node2)
        5
    '''
    path1, path2 = map(lambda x: x.get_subtree_path().split('/'), [node1, node2])
    i = 0
    for (char1, char2) in zip(path1, path2):
        if char1 != char2:
            break
        else:
            i += 1
    return len(path1) + len(path2) - 2*i

class Tree(nn.Module):
    def __init__(self, root):
        super().__init__()
        self.root = root
        self.L, self.J = self.root.num_leaves, 0
        self.leaves, self.nodes = {}, {}
        self.edges = list(self.traverse(self.root))
        # self.mu, self.raw_sigma = self.generate_params(1)
        self.distance_matrix = self.get_distance_matrix()
        self.mask = self.get_mask()
        self.gamma = main_handler.business_config['gamma']
        self.kernel_matrix = self.get_kernel_matrix()
        self.noise_scale = 1e-2

    def node_id2index(self, node_id):
        return list(sorted(self.leaves.keys())).index(node_id)

    def get_alpha(self, x_train, y_train, repeat, device, softplus_bias):
        ''' x_train: list of nodes
            y_train: list of accuracies * 2 - 1
            return: [M, L]
        '''
        def get_mean_and_sigma():
            if not x_train:
                return torch.zeros(self.L).to(device), self.kernel_matrix
            k_train = ((self.kernel_matrix[gold_indices].T)[gold_indices]).T
            noise_eye = self.noise_scale * torch.eye(len(gold_indices)).to(device)
            k_train_inv = (k_train + noise_eye).inverse()
            k_test_train = ((self.kernel_matrix[non_gold_indices].T)[gold_indices]).T
            k_test_test = ((self.kernel_matrix[non_gold_indices].T)[non_gold_indices]).T
            foo = k_test_train @ k_train_inv
            test_y_mean = foo @ y_train
            noise_eye = self.noise_scale * torch.eye(len(non_gold_indices)).to(device)
            test_y_sigma = k_test_test + noise_eye - foo @ k_test_train.T
            return test_y_mean, test_y_sigma
        y_train = torch.tensor(y_train).to(device)
        gold_indices = [self.node_id2index(x.node_id) for x in x_train]
        if len(gold_indices) == self.L:
            return torch.stack([y_train]*repeat).to(device)
        non_gold_indices = [i for i in range(self.L) if i not in gold_indices]
        test_y_mean, test_y_sigma = get_mean_and_sigma()
        noise = torch.normal(0, self.noise_scale, [repeat, len(non_gold_indices)], device=device)
        non_gold_y = noise @ test_y_sigma + test_y_mean
        # FIXME: noise_scale do not regard y's variance
        alpha = torch.zeros(repeat, self.L).to(device)
        alpha[:, non_gold_indices] = non_gold_y
        alpha[:, gold_indices] = y_train
        alpha = F.softplus(alpha+softplus_bias)
        return alpha

    def get_mask(self):
        mask = torch.zeros([self.L, self.L])
        for i, _ in enumerate(list(sorted(self.leaves.keys()))):
            for j, _ in enumerate(list(sorted(self.leaves.keys()))):
                if i == j or self.distance_matrix[i, j] <= main_handler.business_config['distance_threshold']:
                    mask[i, j] = 1
        return mask.to(main_handler.business_config["device"])

    def generate_params(self, K):
        mu = nn.Parameter((torch.randn([K, self.L])/self.L).clone().detach().requires_grad_(True))
        def get_non_singular_matrix(K):
            count = 0
            while count < K:
                raw_sigma = nn.init.orthogonal_(torch.empty([self.L, self.L]))
                if not torch.isnan(raw_sigma.logdet()).item():
                    yield raw_sigma.clone().detach()
                    count += 1
        return mu, nn.Parameter(torch.stack(list(get_non_singular_matrix(K))))

    def get_distance_matrix(self):
        ret = torch.zeros([self.L, self.J])
        for i, leaf in enumerate(self.leaves.values()):
            for j in range(self.J):
                ret[i][j] = distance(leaf, self.nodes[j])
        return nn.Parameter(ret.clone().detach().requires_grad_(False).to(main_handler.business_config["device"]))

    def get_kernel_matrix(self):
        ret = torch.zeros([self.L, self.L])
        for i, leaf1 in enumerate(self.leaves.values()):
            for j, leaf2 in enumerate(self.leaves.values()):
                ret[i][j] = distance(leaf1, leaf2)
        ret = (-(ret*self.gamma)**2).exp()
        return nn.Parameter(ret.clone().detach().requires_grad_(False))

    # Must call this first to initialize J
    def traverse(self, node):
        node.node_id = self.J
        self.J += 1
        self.nodes[node.node_id] = node
        yield (node.node_id, node.node_id)
        if node.children:
            for child in node.children.values():
                yield from self.traverse(child)
                yield (node.node_id, child.node_id)
                yield (child.node_id, node.node_id)
        else:
            self.leaves[node.node_id] = node

    def propogate_up(self, posterior, threshold):
        ''' posterior: [N, L]
            return: [N, J]
        '''
        def do_propogate_up(node):
            if (ret != -1).all():
                return
            if node.children:
                for child in node.children.values():
                    do_propogate_up(child)
                tree_prob[:, node.node_id] = sum(tree_prob[:, child.node_id] for child in node.children.values())
            else:
                tree_prob[:, node.node_id] = posterior[:, self.node_id2index(node.node_id)]
            for i, prob_not_found in enumerate((ret == -1).float() * tree_prob[:, node.node_id]):
                # FIXME: this implementation prefers small node_ids.
                if prob_not_found >= threshold:
                    ret[i] = node.node_id
        tree_prob = torch.zeros([posterior.shape[0], self.J]) #.to(main_handler.business_config["device"])
        ret = -torch.ones(posterior.shape[0], dtype=torch.int32)
        do_propogate_up(self.root)
        return [self.nodes[i.item()] for i in ret]

    def get_subtree(self, posterior, threshold):
        posterior = posterior.to('cpu')
        return self.propogate_up(posterior, threshold)

class UserModel(nn.Module):
    def __init__(self, tree, num_worker, beta):
        super().__init__()
        self.tree, self.beta = tree, beta
        self.J, self.L, self.K = tree.J, tree.L, num_worker
        # self.mu, self.raw_sigma = tree.generate_params(self.K)
        self.reset_gold_count()
        self.zoom = nn.Parameter(torch.tensor(0.4, device=main_handler.business_config['device'], requires_grad=False))

    def reset_gold_count(self):
        self.gold_count = [{} for k in range(self.K)]

    def get_gold_info(self, valid_users):
        def do_get_gold_info(gc):
            for leaf, (right_count, wrong_count) in gc.items():
                accuracy = right_count / (right_count + wrong_count)
                yield leaf, accuracy * main_handler.business_config['accuracy_slope'] + main_handler.business_config['accuracy_bias']
        for i, gc in enumerate(self.gold_count):
            if i in valid_users:
                yield list(do_get_gold_info(gc))

    def add_gold(self, user_id, leaf, is_right):
        gold_count = self.gold_count[user_id]
        if leaf in gold_count:
            gold_count[leaf][is_right] += 1
        else:
            gold_count[leaf] = [1, 0] if is_right else [0, 1]
            # gold_count[leaf] = [2, 1] if is_right else [1, 2]

    def get_sigma(self, raw_sigma):
        sigma = raw_sigma.permute(0, 2, 1) @ raw_sigma
        sigma = sigma * self.tree.mask
        sigma += main_handler.business_config["epsilon"] * torch.eye(self.L).to(main_handler.business_config["device"])
        return sigma

    def get_log_pi(self, alpha):
        ''' In this version, we use only distance based pi generation.
            TODO: More advanced probability generation may be added in the future.
        '''
        logits = torch.einsum('lj,mkl->mklj', -((self.tree.distance_matrix+1e-8) ** self.zoom) * main_handler.business_config["temperature"], alpha)
        return F.log_softmax(logits, dim=3)

    def regularization(self, x, sigma):
        return -((self.mu - self.tree.mu) ** 2).mean(0).sum(0) * self.beta

    def entropy(self, x, log_p, valid_users, repeat=1000):
        ''' x: [N, K, J]
            log_p: [L] log probability of prior distribution of leaves
            log_pi: [M, K, L, J]
            log_post: [M, N, L]
            return: [N] entropy of each question
        '''
        R = main_handler.business_config["repeat_monte_carlo_round"]
        import math
        # FIXME: use alpha_mean
        total_entropy, total_post, total_alpha = 0, 0, 0
        # FIXME: calculating total_post: the sum of logsumexp should be over all samples. We use aveage across rounds now.
        for m in range(R):
            # sigma = self.get_sigma(self.raw_sigma)
            foo = list(self.get_gold_info(valid_users))
            gold_nodes, gold_estimates = [[g[0] for g in f] for f in foo], [[g[1] for g in f] for f in foo]
            alphas = [self.tree.get_alpha(gn, ge, main_handler.business_config['num_monte_carlo_sample'],
                                          main_handler.business_config['device'],
                                          main_handler.business_config['softplus_bias']) for gn, ge in zip(gold_nodes, gold_estimates)]
            alpha = torch.stack(alphas).to(main_handler.business_config['device'])
            alpha = alpha.permute(1, 0, 2)
            log_pi = self.get_log_pi(alpha)
            log_post = log_posterior(x, log_pi, log_p)
            post = log_post.exp()
            total_entropy += -(log_post * post).sum(dim=2).mean(dim=0)
            total_post += log_post.logsumexp(0) - math.log(log_pi.shape[0])
            total_alpha += alpha.mean(0)
        return total_entropy / R, (total_post / R).softmax(1), total_alpha / R

def log_posterior(x, log_pi, log_p):
    ''' x is the same as UserModel.forward
        log_p: [L]
        log_pi: [M, K, L, J], M different samples of log_pi in UserModel.forward
        return: [M, N, L]
    '''
    logits = torch.einsum('nkj,mklj->mnl', x, log_pi) + log_p
    return F.log_softmax(logits, dim=2)


class Model(nn.Module):
    def __init__(self, root, *args, **kwargs):
        super().__init__()
        self.p = nn.Parameter((torch.ones([1, root.num_leaves])/root.num_leaves).log().clone().detach().requires_grad_(False))
        self.tree = Tree(root)
        self.users = UserModel(self.tree, *args, **kwargs)
        self.to(main_handler.business_config["device"])

    def forward(self, x, log_p):
        return self.users(x, F.log_softmax(log_p, dim=1))

    def entropy(self, x, valid_users, repeat=1000):
        x = x[:, valid_users, :]
        return self.users.entropy(x, F.log_softmax(self.p, dim=1), valid_users, repeat=repeat)


if __name__ == '__main__':
    import doctest
    doctest.testmod()
    class Node:
        def __init__(self, name):
            self.name = name
    root = Node('root')
    child1 = Node('root/child1')
    child2 = Node('root/child1/child2')
    child3 = Node('root/child3')
    root.node_id, child1.node_id, child2.node_id, child3.node_id = 0, 1, 2, 3
    root.children = {'child1': child1, 'child3': child3}
    child1.children = {'child2': child2}
    child2.children, child3.children = [], []

    root.num_leaves, root.total_node = 2, 4
    tree = Tree(root)
    model = Model(tree.root, 3, 0.02)
    assert model.users.J == 4
    optimizer = torch.optim.Adam(list(model.parameters()), lr=0.0001)
    x = torch.tensor([[[0, 0, 0, 1], [0, 0, 0, 0], [0, 0, 0, 1.]]])
    with torch.no_grad():
        print(model.entropy(x))
    for i in range(100000):
        loss, reg, log_likelihood = model(x)
        loss.backward()
        if i % 1000 == 0:
            print(loss.item(), reg.item(), log_likelihood.item())
            with torch.no_grad():
                print(model.entropy(x).item())
        optimizer.step()



