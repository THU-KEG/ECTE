from handlers.main_handler import BaseHandler
import handlers.main_handler

recommender = None

class RankingHandler(BaseHandler):

    @staticmethod
    def obfuscate_rate(rate, lower=True, k=5):
        hundred_rate = int(rate * 100)
        if lower:
            return hundred_rate // k * k
        else:
            return (hundred_rate + k - 1) // k * k

    def get(self):
        business_config, data_provider = handlers.main_handler.get_context()
        users = data_provider.exesql("""
          SELECT id, name from users where ignored == 0 and blocked == 0
        """)

        user_to_gold_answer_correct_rate = {user_id: user.correct_rate_and_count[0] for user_id, user in recommender.users.items() if not user.ignored and not user.blocked}
        user_to_gold_answer_count = {user_id: user.correct_rate_and_count[1] for user_id, user in recommender.users.items() if not user.ignored and not user.blocked}
        user_to_total_answer_count = {user_id: user.answer_count for user_id, user in recommender.users.items() if not user.ignored and not user.blocked}
        user_to_total_answer_count_max = max(user_to_total_answer_count.items(), key=lambda x: x[1])[1]
        user_to_gold_answer_score = []
        for user_id in user_to_gold_answer_count:
            count = user_to_gold_answer_count[user_id]
            correct_rate = user_to_gold_answer_correct_rate[user_id]
            total_count = user_to_total_answer_count[user_id]
            if count >= business_config["ranking_min_answers"]:
                w = business_config["correct_rate_weight"]
                score = 1 / (w * 1 / correct_rate + (1-w) * user_to_total_answer_count_max / total_count) if total_count else 0
                user_to_gold_answer_score.append((user_id, score, correct_rate, count))
        user_to_gold_answer_score.sort(key=lambda x: x[1], reverse=True)
        user_to_name = {id: name for id, name in users}

        current_user_id = self.get_current_user_id()
        rank_data = []
        for i, (id, _, rate, count) in enumerate(user_to_gold_answer_score[0: business_config["ranking_top_n"]]):
            is_current_user = current_user_id == id
            rank_data.append((i + 1, user_to_name[id], self.obfuscate_rate(rate), is_current_user, count))

        if current_user_id in [a[0] for a in user_to_gold_answer_score]:
            display_current_user_gold_rate = True
            current_user_gold_rate = self.obfuscate_rate(
                user_to_gold_answer_correct_rate[current_user_id])
            try:
                current_user_gold_rate_ranking = next(t[2] for t in user_to_gold_answer_score if t[0] == current_user_id)
            except StopIteration:
                import pdb; pdb.set_trace()
            current_user_gold_rate_percentage = max(self.obfuscate_rate(current_user_gold_rate_ranking / len(user_to_total_answer_count), lower=False),
                                                    1)

        else:
            display_current_user_gold_rate = False
            current_user_gold_rate = None
            current_user_gold_rate_percentage = None


        feed_dict = {
            'is_admin': self.check_authority(49999),
            'data': rank_data,
            'display_current_user_gold_rate': display_current_user_gold_rate,
            'current_user_gold_rate': current_user_gold_rate,
            'current_user_gold_rate_percentage': current_user_gold_rate_percentage,
        }

        self.render("ranking.html", **feed_dict)
