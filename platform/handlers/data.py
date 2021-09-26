#!/usr/bin/env python3
#coding:utf-8
from __future__ import print_function
'''
	用于数据处理的过程
'''

import json
try:
	from handlers.db import DB
except ModuleNotFoundError:
	from db import DB
import threading


class DataProvider:
	def __init__(self, db):
		#打开数据库
		self.db = DB(db)
		self.target_tags_per_problem = 3
		#计时器dict
		self.timer_dict = {}
	#检查是否通过了测试的三组题
	def check_passed_test(self,user_id):
		return self.db.check_passed_test(user_id = user_id)

	#得到三组测试题
	def get_pass_test(self, user_id):
		res = self.db.select('users', keys=['pass_test'], conditions={'id': user_id})[0][0]
		return res

	def inc_pass_test(self, user_id, pass_test_num):
		self.db.update('users',{'pass_test' : pass_test_num}, {'id' : user_id})

	def inc_group_num(self, user_id):
		self.db.update('users',{'group_num' : self.get_group_num(user_id) + 1}, {'id': user_id})

	def get_group_num(self, user_id):
		res = self.db.select('users', keys=['group_num'], conditions={'id': user_id})[0][0]
		return res

	def get_user_authority(self, user_id):
		res = self.db.select('users', keys=['authority'], conditions={'id': user_id})[0][0]
		return res

	def get_user_blocked(self, user_id):
		res = self.db.select('users', keys=['blocked'], conditions={'id': user_id})[0][0]
		return res

	def exists_user(self, user_id):
		return len(self.db.select('users', conditions={'id': user_id})) != 0

	#检查是否可以开始（有题可标）
	def check_can_start(self, user_id):
		return self.get_new_group(user_id) is not None

	def validate_user(self, name, passwd):
		res = self.db.select('users', keys=['pass', 'id'], conditions={'name': name})
		if len(res) == 0:
			return False, "用户名不存在", None
		elif not res[0][0] == passwd:
			return False, "密码错误.", None
		else:
			return True, None, res[0][1]

	def add_user(self, name, passwd, email, student_id):
		self.db.insert('users', {'name': name, 'pass': passwd, 'email': email, 'student_id': student_id, 'authority': 0})

	def check_name(self, name):
		res = self.db.select('users', conditions={'name': name})
		return len(res) == 0

	#get user's id using his name
	def get_id(self, name):
		return self.db.get_id(name)

	def get_progress(self, user_id):
		return self.db.get_user_progress(user_id)

	def test(self):
		self.db.test()

	def get_test_answer(self, id):
		return self.db.get_test_answer(id)

	def get_test_problem(self, user_id):
		test_process = self.get_pass_test(user_id)
		res = self.db.select_test_problem(test_process)
		if res == []:
			return None
		problems = []
		for i in res:
			item = {}
			item['id'] = i[0]
			item['problem_group_id'] = i[1]
			item['hyponym'] = i[2]
			item['hypernym'] = i[3]
			item['answer'] = i[4]
			item['explaint'] = i[5]
			problems.append(item)
		problems = json.dumps(problems).encode('utf-8').decode('unicode_escape')
		return problems

	def count_test_problem(self):
		return self.db.count("test")

	def get_test_group_count(self):
		return self.db.get_test_group_count()

	@staticmethod
	def problem_tuples_to_dicts(l):
		return [{
			"id": t[0],
			"problem_group_id": t[1],
			"hyponym": t[2],
			"hypernym": t[3] if not t[3].startswith('MERGED') else t[3][len('MERGED/'):]
		} for t in l]

	@staticmethod
	def encode_problem(p):
		return json.dumps(p).encode('utf-8').decode('unicode_escape')

	def count_tagged_problems(self, field=None):
		if field is None:
			touched_problems = self.db._execute("""
				SELECT problem_group_id, user_id
				FROM answer
				GROUP BY problem_group_id
			""", [], True)
			all_problem_count = \
			self.db._execute('SELECT COUNT(distinct problem_group_id) FROM problem', [], True)[0][0]
		else:
			touched_problems = self.db._execute("""
				SELECT answer.problem_group_id, user_id
				FROM answer INNER JOIN problem ON answer.problem_group_id = problem.problem_group_id
				WHERE problem.field="{}"
				GROUP BY answer.problem_group_id
			""".format(field), [], True)
			all_problem_count = self.db._execute('''
				SELECT COUNT(distinct problem.problem_group_id)
				FROM answer INNER JOIN problem ON answer.problem_group_id = problem.problem_group_id
				WHERE problem.field="{}"'''
			.format(field), [], True)[0][0]


		_blacklisted_user = self.db.get_all_blocked_or_ignored_users()
		blacklisted_user = set([_user_id for _user_id, _, _ in _blacklisted_user])

		tags, valid_tags, finished = 0, 0, 0
		groups = {}
		for group_id, user_id in touched_problems:
			tags += 1
			if user_id not in blacklisted_user:
				if group_id in groups:
					groups[group_id].append(user_id)
				else:
					groups[group_id] = [user_id]
				valid_tags += 1
				if len(groups) == self.target_tags_per_problem:
					finished += 1

		return tags, valid_tags, finished, all_problem_count

	def save_answer(self, user_id, answer):
		REPEAT_SENDING = 2
		SAVE_SUCCESS = 1

		# 对于所有的答案
		item = answer
		id = item['actualId']
		problem_answer = item['answer']
		cost_time = item['cost_time']
		res = self.exesql(f"select * from answer where problem_group_id = {id} and user_id = {user_id}")
		if len(res) > 0:
			return REPEAT_SENDING
		self.db.insert('answer',{
						'user_id': user_id,
						'problem_group_id': id,
						'cost_time': cost_time,
						'answer': answer['answer'],
						'is_diamond': 0,
						'is_redundant': 0,
						'number': answer['number'],
						'round': answer['round'],
						'subtree_root': answer['hypernym']
					})
		return SAVE_SUCCESS

	def end_problem(self, problem_group_id):
		self.db.update('problem', {'isdone' : 1}, {'problem_group_id' : problem_group_id})

	def save_feedback(self, data):
		self.db.insert('feed_back', {'user_id': data['user_id'], 'problem_group_id' : data[u'problem_group_id'], 'content' : data[u'content']})
	
	def problem_timer(self,problem_group_id):
		self.db.update('problem', {'isdone' : 0}, {'problem_group_id' : problem_group_id})

	def problem_ing(self,problem_group_id):
		self.db.update('problem', {'isdone' : -1}, {'problem_group_id' : problem_group_id})

	def reset_test(self, user_id):
		self.db.update('users', {'pass_test' : 0}, {'pass_test' : 3, 'id': user_id})

	def exesql(self, sql, select=True):
		return self.db.exesql(sql, [], select)


if __name__ == "__main__":
	pass
