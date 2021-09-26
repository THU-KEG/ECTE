import json

class TaxNode:
    node_dict = {}
    total_node = 0
    def __init__(self, name, parent=None):
        self.name = name
        self.parent = parent
        self.children = dict()
        if parent:
            parent.children[self.name] = self
        self.depth_from_root = self.parent.depth_from_root + 1 if self.parent else 1
        self.height_from_leaf = 0
        self.specificity = 0
        TaxNode.total_node += 1
        self.node_id = TaxNode.total_node
        TaxNode.node_dict[self.node_id] = self
    def __eq__(self, other):
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)

    @property
    def num_leaves(self):
        if self.children:
            return sum(child.num_leaves for child in self.children.values())
        else:
            return 1

    @property
    def leaves(self):
        if self.children:
            leaves = []
            for child in self.children.values():
                leaves += child.leaves
            return leaves
        else:
            return [self]

    @property
    def nodes(self):
        nodes = [self]
        if self.children:
            for child in self.children.values():
                nodes += child.nodes
        return nodes

    def get_ancestor_by_depth(self, depth):
        node = self
        while node.depth_from_root > depth:
            node = node.parent
        return node

    def path_from_root(self):
        return self.get_subtree_path()

    def get_subtree_path(self):
        string_list = list()
        node = self
        while True:
            string_list.append(node.name)
            if not node.parent:
                break
            else:
                node = node.parent
        string_list.reverse()
        return '/'.join(string_list)

    def find_node(self, path):
        subpath = '/'.join(path.split('/')[1:])
        return self.do_find_node(subpath)

    def do_find_node(self, path):
        if not path:
            return self
        else:
            this_level_path, *others = path.split('/')
            return self.children[this_level_path].do_find_node('/'.join(others))

    def calculate_height_and_specificity_from_leaf(self):
        """
        calculate the height from leaf using dfs
        should be called by root node
        function H(x_g)
        :return: int max height
        """
        if not self.children:
            self.specificity = 1
            return 0
        if self.children:
            children_height_list = list()
            for child in self.children.values():
                children_height_list.append(child.calculate_height_and_specificity_from_leaf())
            self.height_from_leaf = max(children_height_list) + 1
            self.specificity = self.depth_from_root / (self.depth_from_root + self.height_from_leaf)
        return self.height_from_leaf

    @staticmethod
    def has_hyper_or_hypo_relationship(label, node):
        """
        retrieve from the deeper node to shallow node based on the depth gap
        function M(x_g, x_h)
        :param label: x_g
        :param node: x_h
        :return: boolean
        """
        if label.depth_from_root <= node.depth_from_root:
            depth_gap = node.depth_from_root - label.depth_from_root
            shallow_node = label
            deep_node = node
        else:
            depth_gap = label.depth_from_root - node.depth_from_root
            shallow_node = node
            deep_node = label
        while depth_gap > 0:
            deep_node = deep_node.parent
            depth_gap = depth_gap - 1
        return deep_node.name == shallow_node.name

    @staticmethod
    def measure_fitness(label, node):
        """
        measure fitness of 2 node M_s(x_g, x_h)
        :param label: x_g
        :param node: x_h
        :return: float
        """
        if not TaxNode.has_hyper_or_hypo_relationship(label, node):
            return 0
        else:
            return label.specificity / node.specificity

    @staticmethod
    def get_common_ancestor_node(answers):
        if not answers:
            return None
        min_depth_from_root = min([answer.depth_from_root for answer in answers])
        init_nodes = [answer.get_ancestor_by_depth(min_depth_from_root) for answer in answers]
        counter = 0
        length = len(init_nodes)
        while True:
            if len(set([node.name for node in init_nodes])) == 1:
                break
            index = counter % length
            init_nodes[index] = init_nodes[index].parent
            counter = counter + 1
        return init_nodes[0]