import logging
import sqlite3
import tqdm
import torch
import random
import json
from handlers import main_handler
from .user import User
from .question import Question
from .replay import ReplayBuffer
from .inference import Model
import os
try:
    from .tax_node import TaxNode
except ModuleNotFoundError:
    from .tax_node import TaxNode
    from .data import DataProvider


class Recommender:
    def __init__(self, data_provider, instance_filename, num_users=0, eval=False, log_filename=None):
        self.should_finish = False
        self.alpha = main_handler.business_config['alpha']
        self.budget = main_handler.business_config['budget']
        self.diamond_limit = main_handler.business_config['diamond_limit']
        self.data_provider = data_provider
        self.total_questions = {}
        self.redundance_buffer = {}
        self.current_questions = list()
        self.users = {}
        self.gold_answer_from_instances = {}
        with open(instance_filename) as f:
            for line in f:
                concept, path = line.split()
                concept, path = concept.strip(), path.strip()
                self.gold_answer_from_instances[concept] = path
        logging.info("init_tree")
        self.init_tree()
        logging.info("init_model")
        self.init_model()
        logging.info("init_questions")
        self.init_questions()
        self.init_users(num_users)
        # XXX: reverse order add_question for evaluation in each round is wrong because not reset buffer.
        self.accs = []
        rounds = self.data_provider.exesql(f"SELECT DISTINCT round from {main_handler.business_config['answer_table_name']}")
        rounds = list(sorted([r[0] for r in rounds]))
        if eval:
            for r in rounds:
            # # r = 999999
                logging.info(f"evaluating until round {r}...")
                self.model.users.reset_gold_count()
                self.add_questions(r)
                logging.info(f"{sum([len(q.answers) == 15 for q in self.total_questions.values()])} questions reaches r_max")
                self.accs.append(self.eval())
                logging.warn(self.accs)
                with open(log_filename, 'w') as f:
                    json.dump(self.accs, f)
        else:
            self.add_questions(99999)
        # self.calculate_estimation_quality()
        self.leaves_dict, self.nodes = {}, {}
        self.J = 0
        self.init_leaves_dict(self.tree)

    def init_leaves_dict(self, node):
        node.node_id = self.J
        self.J += 1
        self.nodes[node.node_id] = node
        if node.children:
            for child in node.children.values():
                self.init_leaves_dict(child)
        else:
            self.leaves_dict[node.node_id] = node

    def node_id2index(self, node_id):
        return list(sorted(self.leaves_dict.keys())).index(node_id)

    def add_user(self, user_id):
        self.users[user_id] = User(user_id, self)
        self.users[user_id].alpha = torch.zeros(self.model.tree.L)
        return self.users[user_id]

    def next_number(self):
        self._number += 1
        return self._number

    def init_tree(self):
        with open(main_handler.business_config['tree_file']) as f:
            node = json.load(f)[0]
        def construct_node(node, parent=None):
            taxnode = TaxNode(node['name'], parent)
            if 'children' in node:
                for child in node['children']:
                    construct_node(child, taxnode)
            return taxnode
        self.tree = construct_node(node)

    def init_users(self, num_users):
        user_ids = self.data_provider.exesql(f"SELECT id FROM {main_handler.business_config['user_table_name']}")
        user_ids = [int(u[0]) for u in user_ids]
        for user_id in tqdm.tqdm(user_ids):
            user = self.add_user(user_id)
            for question in self.total_questions.values():
                if user.user_id in question.answers:
                    user.answered_questions.append(question)
            user.answer_count = len(user.answered_questions)
            user.diamond_count = self.data_provider.exesql(f"select count(problem_group_id) from answer "
                                                           f"where user_id = {user.user_id} and is_diamond != 0")[0][0]
            self.users[user_id] = user

    def init_prob(self):
        for user in tqdm.tqdm(self.users.values()):
            if user.ignored:
                continue
            for question in user.answered_good_questions:
                user.update_prob_by_answering(question, question.answers[user.user_id])

    def init_model(self):
        self.model = Model(self.tree, main_handler.business_config["num_worker"], main_handler.business_config["beta"])
        self.optimizer = torch.optim.Adam(self.model.parameters(), main_handler.business_config["learning_rate"])
        # if os.path.exists(main_handler.business_config['model_name']):
            # state = torch.load(main_handler.business_config['model_name'])
            # self.model.load_state_dict(state['model'])
            # self.optimizer.load_state_dict(state['optimizer'])

    def add_questions(self, round):
        question_iter = self.data_provider.exesql(f"SELECT DISTINCT * FROM {main_handler.business_config['table_name']} WHERE field = '{main_handler.business_config['field']}'")
        # Assuming all gold are to leaf
        for question in question_iter:
            if question[2]:
                gold_answer = question[2]
                gold_answer_node = self.tree.find_node(question[2])
                if gold_answer_node.children:
                    logging.debug(f"question {question[0]}'s gold_answer is not a leaf. Ignoring it...'")
                    gold_answer = None
                    gold_index = None
                else:
                    gold_index = list(sorted(self.model.tree.leaves.keys())).index(gold_answer_node.node_id) if main_handler.business_config['visible_gold_rate'] else None
            else:
                logging.debug(f"question {question[0]} has no gold answer")
                gold_answer = None
                gold_index = None
            answers = {}
            try:
                question_iter = self.data_provider.exesql(f"select user_id, answer from {main_handler.business_config['answer_table_name']} where problem_group_id = {question[0]} and round <= {round} and is_diamond = 0 and is_redundant = 0")
            except sqlite3.OperationalError:
                question_iter = self.data_provider.exesql(f"select user_id, answer from {main_handler.business_config['answer_table_name']} where problem_group_id = {question[0]} and round <= {round} and is_diamond = 0")
            for user_id, answer_str in question_iter:
                answer = self.tree.find_node(answer_str)
                answers[user_id] = answer
                self.buffer.add(question[0], user_id, answer, gold_index)
                if gold_answer:
                    self.model.users.add_gold(user_id, gold_answer_node, gold_answer == answer_str)
            # TODO: is_gold_visible
            self.total_questions[question[0]] = Question(question_id=question[0],
                                                        answers=answers,
                                                        concept=question[1],
                                                        gold_answer=gold_answer)

    def init_questions(self):
        self.diamond_id_threshold = self.data_provider.exesql(f"select max(problem_group_id) from problem")[0][0]
        if self.diamond_id_threshold is None:
            self.diamond_id_threshold = -1
        else:
            self.diamond_id_threshold = int(self.diamond_id_threshold)
        self.max_question_id = self.data_provider.exesql(f"select max(problem_group_id) from answer")[0][0]
        if self.max_question_id is None:
            self.max_question_id = -1
        else:
            self.max_question_id = int(self.max_question_id)
        self.max_question_id = max(self.max_question_id, self.diamond_id_threshold) + 1
        question_iter = self.data_provider.exesql(f"SELECT DISTINCT * FROM {main_handler.business_config['table_name']} WHERE field = '{main_handler.business_config['field']}'")
        self._number = self.data_provider.exesql(f"SELECT MAX(number) FROM {main_handler.business_config['answer_table_name']}")[0][0]
        self.round = self.data_provider.exesql(f"SELECT MAX(round) FROM {main_handler.business_config['answer_table_name']}")[0][0]

        if self._number is None:
            self._number = -1
        if self.round is None:
            self.round = -1
        # XXX: make sure soted by id and id is unique
        self.total_questions = {}
        self.buffer = ReplayBuffer(main_handler.business_config["num_worker"], self.tree.total_node, self.tree.num_leaves, len(question_iter))
        # self.current_questions = list(self.total_questions.values())

    def leaf_matrix_index_to_path(self, index):
        # FIXME: speed?
        # FIXME: index2node_id and node_id2index should be transparent
        node_id = list(sorted(self.model.tree.leaves.keys()))[index]
        return self.model.tree.leaves[node_id].path_from_root()

    def precision_at_k(self, top_k, gold_answers):
        hit_at_k, answer_count = 0, 0
        assert len(top_k[0]) == len(gold_answers)
        for gold_answer, top_k_option in zip(gold_answers, top_k.indices):
            if gold_answer is None:
                assert False
                continue
            top_k_answers = [self.leaf_matrix_index_to_path(o.item()) for o in top_k_option]
            hit_at_k += (gold_answer in top_k_answers)
            answer_count += 1
        return (hit_at_k / answer_count) if answer_count else 0.0

    def mean_gold_answer_prob(self, mean_posterior, gold_answers):
        total_prob, gold_count = 0, 0
        assert len(mean_posterior) == len(gold_answers)
        for gold_answer, mp in zip(gold_answers, mean_posterior):
            if gold_answer is None:
                continue
            gold_leaf = self.tree.find_node(gold_answer)
            # FIXME: speed?
            index = list(sorted(self.model.tree.leaves.keys())).index(gold_leaf.node_id)
            total_prob += mp[index]
            gold_count += 1
        return (total_prob / gold_count) if gold_count else 0.0

    def print_train_status(self, x, question_ids, k=1):
        with torch.no_grad():
            entropy, posterior, _ = self.model.entropy(torch.from_numpy(x).to(main_handler.business_config['device']).float(),
                list(self.users.keys()),
                main_handler.business_config["num_monte_carlo_sample"])
            subtree_roots = self.model.tree.get_subtree(posterior, main_handler.business_config['subtree_probability_threshold'])
            logging.info([r.name for r in subtree_roots])
            gold_answers = [self.gold_answer_from_instances[self.total_questions[qid].concept] for qid in question_ids]
            top_k = posterior.topk(k, dim=1)
            precision_at_k = self.precision_at_k(top_k, gold_answers)
            logging.debug(f"precision_at_top_k = {precision_at_k}")
            logging.info(f"mean_gold_answer_prob = {self.mean_gold_answer_prob(posterior, gold_answers)}")
            logging.info(f"batch entropy mean = {entropy.mean().item():4f}, batch entropy std = {entropy.std().item():4f}")
            for i in range(len(question_ids)):
                if gold_answers[i]:
                    logging.debug(f"sample gold: {gold_answers[i]}")
                    logging.debug(f"top_k: {[self.leaf_matrix_index_to_path(o.item()) for o in top_k.indices[i]]}")
                    logging.debug({user_id: node.path_from_root() for user_id, node in self.total_questions[question_ids[i]].answers.items()})
            return precision_at_k

    def eval(self):
        self.model.eval()
        right, total = 0, 0
        for i in range(1):
            question_ids = list(self.total_questions.keys())
            random.shuffle(question_ids)
            question_ids = question_ids[:main_handler.business_config["batch_size"]]
            question_ids, x, log_p = self.buffer.sample(main_handler.business_config["batch_size"], question_ids)
            right += self.print_train_status(x, question_ids) * len(x)
            total += len(x)
        acc = right / total
        logging.info(f"average top_k accuracy: {acc}")
        return acc


    def answer_diamond(self, user_id):
        self.users[user_id].diamond_count += 1
        self.max_question_id += 1

    def answer(self, user_id, group_id, option, answer_round):
        question = self.total_questions[group_id]
        self.users[user_id].answer_count += 1
        if question in self.current_questions:
            # The following statement will be executed when answered question in
            # current questions pool, there are two situations:
            # 1 the problem is from current recommending iteration
            # 2 the problem is from last recommending iteration
            # the two situations need update user and question
            # if from current then the database is correct
            # else from last then need handle this late answer
            self.current_questions.remove(question)
            self.users[user_id].answered_questions.append(question)
            answer_node = self.tree.find_node(option)
            question.answers[user_id] = answer_node
            self.buffer.add(group_id, user_id, answer_node)
            if question.gold_answer:
                self.model.users.add_gold(user_id, self.tree.find_node(question.gold_answer), question.gold_answer == option)
            if answer_round != self.round:
                self.data_provider.db.update('answer', {'round': self.round, 'number': self._number},
                                             {'user_id': user_id, 'problem_group_id': group_id})
        else:
            # The following will be executed when there is answered question from
            # last iteration but it is not in current iteration questions pool, then
            # we need store it in the redundancy buffer, these answered questions will
            # be examined in start_new_iteration. These questions need add to user and question
            # and update database at the same time, so it can use answer()
            if group_id in self.redundance_buffer:
                self.redundance_buffer[group_id].append((user_id, group_id, option, answer_round))
            else:
                self.redundance_buffer[group_id] = [(user_id, group_id, option, answer_round)]
            # saveAnswer is_redundant default: 0, so if answer is redundant it needs update
            self.data_provider.db.update('answer', {'is_redundant': 1},
                                         {'user_id': user_id, 'problem_group_id': group_id})

    def recommend_diamond(self, user_id):
        if self.users[user_id].diamond_count <= self.diamond_limit:
            leaf = random.choice(self.tree.leaves)
            return leaf.name, leaf.get_subtree_path()
        else:
            raise RuntimeError(f"user {user_id} got enough diamond questions")

    def save_model(self, epoch=0):
        return
        state = {
            'model': self.model.state_dict(),
            'optimizer': self.optimizer.state_dict()
        }
        torch.save(state, f"{main_handler.business_config['model_name']}_{epoch:03d}")

    def calculate_tree(self):
        def batch_up():
            ret = []
            for question in self.total_questions.values():
                ret.append(question)
                if len(ret) == main_handler.business_config["batch_size"]:
                    yield ret
                    ret = []
            yield ret
        for batch in tqdm.tqdm(list(batch_up())):
            if not batch:
                continue
            with torch.no_grad():
                x = torch.stack([question.to_array(main_handler.business_config["num_worker"], self.tree.total_node) for question in batch]).to(main_handler.business_config["device"])
                entropy, posterior, alphas = self.model.entropy(x, list(self.users.keys()), main_handler.business_config["num_monte_carlo_sample"])
                for alpha, user in zip(alphas, self.users.values()):
                    user.alpha = alpha
                subtree_roots = self.model.tree.get_subtree(posterior, main_handler.business_config['subtree_probability_threshold'])
                for e, q, r, p in zip(entropy, batch, subtree_roots, posterior):
                    q.estimation_quality = e.item()
                    q.subtree_root = r
                    q.posterior = p

    def calculate_estimation_quality(self):
        # self.train()
        self.calculate_tree()
        if self.round > 1:
            self.eval()
        self.save_model()

    def start_new_crowd_iteration(self):
        self.round += 1
        for question in self.total_questions.values():
            question.given_time = 0
            valid_answer_count = len([i for i in question.answers.keys() if not self.users[i].ignored])
            if valid_answer_count >= main_handler.business_config["max_answers_per_question"]:
                question.is_task_valid = False
            else:
                question.is_task_valid = True
        N = max(1, min(int(self.alpha * len(self.total_questions)),
                       len([i for i in self.total_questions.values() if i.is_task_valid])))
        sorted_questions = sorted(list(self.total_questions.values()),
                                  key=lambda x: x.estimation_quality, reverse=True)
        logging.debug([q.estimation_quality for q in sorted_questions])
        for i in range(N):
            if sorted_questions[i].is_task_valid:
                self.current_questions.append(sorted_questions[i])
        logging.debug([q.estimation_quality for q in self.current_questions])
        print('start new iteration, N is ', len(self.current_questions))
        self.should_finish = (len(self.current_questions) == 0)
        self.budget -= len(self.current_questions)
        if self.budget <= 0:
            raise RuntimeError(f"budget is running out and the program should be terminated")

    def update_redundance_buffer(self):
        remove_list = list()
        for question in self.current_questions:
            group_id = question.question_id
            if group_id in self.redundance_buffer:
                remove_list.append(self.redundance_buffer[group_id].pop())
                if len(self.redundance_buffer[group_id]) == 0:
                    self.redundance_buffer.pop(group_id)
        for item in remove_list:
            (user_id, group_id, option, answer_round) = item
            question = self.total_questions[group_id]
            self.current_questions.remove(question)
            self.users[user_id].answered_questions.append(question)
            question.answers[user_id] = self.tree.find_node(option)
            self.data_provider.db.update('answer', {'round': self.round, 'is_redundant': 0},
                                         {'user_id': user_id, 'problem_group_id': group_id})

    def no_more_than_max_answer_per_question(get_next_question):
        def foo(self, *args, **kwargs):
            q, subtree = get_next_question(self, *args, **kwargs)
            while q is not None:
                valid_answer_count = len([i for i in q.answers if not self.users[i].ignored])
                if valid_answer_count >= main_handler.business_config["max_answers_per_question"]:
                    field = main_handler.business_config['field']
                    try:
                        logging.waring(f"stopped in the decorator, error occurs")
                        self.unfinished_questions[field].remove(q)
                        logging.warning(f"question {q.group_id} has been answered {valid_answer_count} times but still in `unfinished_questions`. It is now removed.")
                    except KeyError:
                        logging.warning(f"question {q.group_id} has been answered {valid_answer_count} times and not in unfinished_questions but it is recommended.")
                    q, subtree = get_next_question(self, *args, **kwargs)
                else:
                    break
            return q, subtree
        return foo

    @no_more_than_max_answer_per_question
    def recommend(self, user_id):
        if not self.current_questions:
            self.calculate_estimation_quality()
            self.start_new_crowd_iteration()
        else:
            for question in self.current_questions:
                valid_answer_count = len([i for i in question.answers.keys() if not self.users[i].ignored])
                if valid_answer_count >= main_handler.business_config["max_answers_per_question"]:
                    question.is_task_valid = False
                else:
                    question.is_task_valid = True
        problem = self.users[user_id].exploit()
        subtree_path = problem.subtree_root.get_subtree_path()
        self.current_questions.remove(problem)
        self.current_questions.append(problem)
        logging.info(f"current pool size: {len(self.current_questions)}")
        return problem, subtree_path


if __name__ == '__main__':
    import sys
    assert sys.argv[1] in ['add_gold', 'mask_labels', 'debug', 'eval']
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    # db_name = "aminer-taxonomy-to-label/aminer_tagging.db"
    db_name = sys.argv[2]
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    dp = DataProvider(db_name)
    if sys.argv[1] == 'eval':
        recommender = Recommender(dp, eval=True)
        with open(db_name+'.log', 'w') as f:
            json.dump(recommender.accs, )
        sys.exit(0)
    recommender = Recommender(dp)
    if sys.argv[1] == 'debug':
        import ipdb; ipdb.set_trace()
    elif sys.argv[1] == 'add_gold':
        global_id = [max(q for q in recommender.questions)]
        some_user = recommender.users[0]
        merged = some_user.mcts["MERGED"]

        finest_grain_count = merged.group_option_count[3]
        decay = 0.707
        for depth in reversed(range(1, 3)):
            expected_count = finest_grain_count * decay
            add_count = merged.group_option_count[depth]
            progress_bar = tqdm.tqdm(initial=add_count, total=expected_count)
            while add_count < expected_count:
                foo, bar = merged.random_child(depth).generate_a_pair_of_swapped_gold_questions(global_id)
                if foo and bar:
                    foo.insert_db()
                    bar.insert_db()
                    add_count += 2
                    progress_bar.update(2)
            decay *= decay
            progress_bar.close()
    elif sys.argv[1] == 'mask_labels':
        mask_labels(recommender)
    import sys
    sys.exit(0)
    import matplotlib.pyplot as plt
    for q in recommender.questions.values():
        for i, user_id in enumerate(q.answers):
            if i >= 3:
                break
            if q.leaf.is_good:
                q.mock_choose(recommender.users[user_id])
    final_result = {k: q.predict() for k, q in recommender.questions.items()}

    right_log = {field: [] for field in main_handler_bussiness_config["visible_fields"]}

    cursor.execute("select distinct problem_group_id, user_id, time from tagging_log order by date(time)")
    tagging_log1 = cursor.fetchall()
    for field in main_handler_bussiness_config["visible_fields"]:
        for q in recommender.questions.values():
            q.prob = np.ones(q.num_options) / q.num_options
        predicted_result = {k: recommender.questions[k].predict() for k in final_result if recommender.questions[k].leaf.leaf_id.startswith(field)}
        right_num = sum(1 for k, v in final_result.items() if predicted_result[k] == v)
        tagging_log = [tl for tl in tagging_log1 if tl[0] in predicted_result and tl[1] in recommender.users]
        i = 0
        for problem_group_id, user_id, tag_time in tagging_log:
            if recommender.questions[problem_group_id].leaf.leaf_id.startswith(field):
                old_prediction = predicted_result[problem_group_id]
                try:
                    new_prediction = recommender.questions[problem_group_id].mock_choose(recommender.users[user_id])
                except KeyError:
                    logging.warning(f"{user_id} answered {problem_group_id} at {tag_time} but not recorded")
                    continue
                if new_prediction != old_prediction:
                    right_num += 1 if final_result[problem_group_id] == new_prediction else -1
                    right_log[field].append((i, right_num))
                    predicted_result[problem_group_id] = new_prediction
                i += 1
        rl = right_log[field]
        plt.plot([r[0]/rl[-1][0] for r in rl], [r[1]/rl[-1][1] for r in rl], label="ours")
        # plt.plot([r[0]/right_log[field][-1][0] for r in right_log[field]], [r[1]/right_log[field][-1][1] for r in right_log[field]])
