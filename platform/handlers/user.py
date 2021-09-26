import logging
import time
import tqdm


class User:
    def __init__(self, user_id, recommender=None):
        assert type(user_id) is int
        self.user_id = user_id
        self.answered_questions = []
        self.answer_count = 0
        self.diamond_count = 0
        if recommender:
            self.recommender = recommender
            from . import main_handler
            self.ignored = bool(
                main_handler.data_provider.exesql(f"SELECT ignored FROM users WHERE id = {self.user_id}")[0][0])
            self.blocked = bool(
                main_handler.data_provider.exesql(f"SELECT blocked FROM users WHERE id = {self.user_id}")[0][0])
            if self.ignored:
                logging.info(f"user {self.user_id} is ignored")
            if self.blocked:
                logging.info(f"user {self.user_id} is blocked")

    def ignore_me(self, is_init=False):
        if self.ignored and not is_init:
            logging.warning(f"Trying to ignore {self.user_id} which has already been ignored. Action canceled")
            return
        self.ignored = True
        logging.info(f"exceed_max_answers_count = {self.recommender.exceed_max_answers_count} + {len(self.answered_questions)}")
        self.recommender.exceed_max_answers_count += len(self.answered_questions)
        logging.info(f"Ignoring user {self.user_id}")
        for question in tqdm.tqdm(self.answered_questions):
            question.unchoose(self)

    def release_me(self):
        if not self.ignored:
            logging.warning(f"Trying to release {self.user_id} which has not been ignored. Action canceled")
            return
        self.ignored = False
        logging.info(f"exceed_max_answers_count = {self.recommender.exceed_max_answers_count} - {len(self.answered_questions)}")
        self.recommender.exceed_max_answers_count -= len(self.answered_questions)
        logging.info(f"Releasing user {self.user_id}")
        for question in tqdm.tqdm(self.answered_questions):
            question.choose(self, question.answers[self.user_id])

    def exploit(self):
        best_question, best_match_score = None, -999999
        for question in self.recommender.current_questions:
            if question.is_task_valid and self.user_id not in question.answers:
                question.given_time = time.time()
                try:
                    # Ours algorithm
                    score = (question.posterior @ self.alpha)
                except AttributeError:
                    # KBIS algorithm directly return `question`
                    return question
                logging.debug(f"{self.user_id} is not in {question.question_id}'s answers: {question.answers.keys()}")
                logging.debug(f"{self.user_id} and {question.question_id}'s score is {score}'")
                if score > best_match_score:
                    best_question = question
                    best_match_score = score
        if not best_question:
            raise RuntimeError(f"User {self.user_id} has been assigned all his/her valid questions in current question pool.\n "
                                f"But he/she may not answer it. Anyway there is no more to recommend.")
        logging.info(f"recommending {best_question.question_id} for {self.user_id}")
        return best_question

    def get_partial_accuracy(self, answered_questions):
        correct_count = 0
        total_count = 0
        for question in answered_questions:
            if self.user_id in question.answers:
                answer_node = question.answers[self.user_id]
                if answer_node.get_subtree_path() == question.gold_answer:
                    correct_count += 1
            else:
                total_count += 1
        if total_count:
            self.partial_accuracy = correct_count / total_count