#!/usr/bin/env python3
# coding:utf8
'''
    负责前端展示逻辑，处理get，post请求。
    路由请查看url.py


    业务逻辑为 三层
    main_handler.py 前端展示逻辑 
    data.py 数据处理相关函数
    db.py 数据库增删改查
'''
import tornado
from tornado.web import RequestHandler
from .tax_node import TaxNode
from .user import User
import json
import os.path
import threading
import re
import datetime
import hashlib
import functools
import pandas as pd
import tempfile
import time
import io
import xlrd
import random

business_config = {}
data_provider = None
recommender = None
tree = None

def get_context():
    return business_config, data_provider

def fen2yuan(x):
    return "%.2f" % (x / 100)

def yuan2fen(x):
    return int(float(x) * 100)

@functools.lru_cache()
def get_all_fields():
    cmd = """
    SELECT DISTINCT field 
    FROM problem
    """
    result = data_provider.exesql(cmd)

    return [ x for x, in result ]

def get_all_unfinished_fields():
    """
    TODO!
    """
    cmd = """
    SELECT DISTINCT field 
    FROM problem
    """
    result = data_provider.exesql(cmd)

    return [ x for x, in result ]

@functools.lru_cache()
def get_field_to_test_cnt():
    cmd = """
    SELECT field, COUNT(DISTINCT problem_group_id)
    FROM test
    GROUP BY field
    """

    result = data_provider.exesql(cmd)
    return {field: count for field, count in result}

def get_user_field_to_test_cnt(user_id):
    cmd = """
    SELECT field, COUNT(DISTINCT test.problem_group_id)
    FROM test INNER JOIN tagging_log ON test.problem_group_id = tagging_log.problem_group_id
    WHERE tagging_log.type = "TEST" and tagging_log.user_id = "{}"
    GROUP BY field
    """.format(user_id)

    result = data_provider.exesql(cmd)
    return {field: count for field, count in result}

def get_user_field_to_tagged_problem_cnt(user_id):
    cmd = """
    SELECT field, COUNT(DISTINCT problem.problem_group_id)
    FROM problem INNER JOIN tagging_log ON problem.problem_group_id = tagging_log.problem_group_id
    WHERE tagging_log.type = "PROBLEM" and tagging_log.user_id = "{}"
    GROUP BY field
    """.format(user_id)

    result = data_provider.exesql(cmd)
    return {field: count for field, count in result}

def get_test_problem(user_id, field):
    cmd = """
    SELECT id, problem_group_id, hyponym, hypernym, answer, explaint
    FROM test
    WHERE test.problem_group_id = (
        SELECT test.problem_group_id 
        FROM test
        WHERE test.field = "{}" and test.problem_group_id not in (
            SELECT tagging_log.problem_group_id
            FROM tagging_log
            WHERE tagging_log.user_id == "{}" and tagging_log.type == "TEST"
        )
        LIMIT 1
    )
    ORDER BY test.id
    """.format(field, user_id)

    result = data_provider.exesql(cmd)
    return [{
        "id": id,
        "problem_group_id": problem_group_id,
        "hyponym": hyponym,
        "hypernym": hypernym,
        "answer": answer,
        "explaint": explaint
    } for id, problem_group_id, hyponym, hypernym, answer, explaint in result ]


def check_user_authority(level):
    def _check_user_authority(func):
        def wrapper(self, *args, **kwargs):
            if self.check_authority(level) == False:
                for cookie in self.all_cookies:
                    self.clear_cookie(cookie)
                self.redirect("/")
            else:
                func(self, *args, **kwargs)
        return wrapper
    return _check_user_authority


def get_problem(user_id, field):
    _blacklisted_user = data_provider.db.get_all_blocked_or_ignored_users()
    blacklisted_user = set([_user_id for _user_id, _, _ in _blacklisted_user])
    if user_id in blacklisted_user:
        return None
    if random.random() < business_config['diamond_rate']:
        concept, subtree_path = recommender.recommend_diamond(user_id)
        question_id = recommender.diamond_id_threshold + 1
    else:
        problem, subtree_path = recommender.recommend(user_id)
        concept = problem.concept
        question_id = problem.question_id
    return [{'hypernym': subtree_path,
                'hyponym': concept,
                'id': question_id,
                'problem_group_id': question_id,
                'number': recommender.next_number(),
                'round': recommender.round}]

def get_user_tagging_count(user_id):
    cmd = """
    SELECT COUNT(DISTINCT(problem_group_id))
    FROM tagging_log
    WHERE user_id = '{}' and type = 'PROBLEM'
    """.format(user_id)
    return data_provider.exesql(cmd)[0][0]

def get_user_invitations(user_id):
    cmd = """
    SELECT SUM(u1.group_num)
    FROM users as u1 
    JOIN users as u2
    ON u1.inviter_mail = u2.email
    WHERE u2.id = '{}'
    GROUP BY u1.inviter_mail
    """.format(user_id)
    result = data_provider.exesql(cmd)
    if len(result) > 0 and len(result[0]) > 0:
        return result[0][0]
    else:
        return 0

def get_all_user_invitations():
    cmd = """
    SELECT u2.id, SUM(u1.group_num)
    FROM users as u1 
    JOIN users as u2
    ON u1.inviter_mail = u2.email
    GROUP BY u1.inviter_mail
    """

    return {user_id : invited_tags for user_id, invited_tags in data_provider.exesql(cmd)}


check_user_exists = check_user_authority(0)

#基类，提供通用method
class BaseHandler(RequestHandler):

    all_cookies = ["field", "username", "user_id"]

    def get_current_user(self):
        #从session中获取username
        return self.get_secure_cookie("username")

    def get_current_user_id(self):
        return int(self.get_secure_cookie("user_id").decode())

    def check_cookie_integrity(self):
        for cookie in self.all_cookies:
            if self.get_secure_cookie(cookie) is None:
                return False
        return True

    def check_authority(self, level):
        user_id = int(self.get_secure_cookie("user_id").decode())
        if not data_provider.exists_user(user_id) or data_provider.get_user_authority(user_id) < level:
            return False
        else:
            return True

#首页
class MainHandler(BaseHandler):
    #未登录无法执行下列方法，自动跳转到login页面
    @tornado.web.authenticated
    @check_user_exists
    def get(self):

        if self.check_cookie_integrity() is False:
            self.redirect("/")
            return

        feed_dict = {}
        username = tornado.escape.xhtml_escape(self.current_user)
        user_id = int(self.get_secure_cookie("user_id").decode("utf-8"))
        feed_dict['username'] = username
        feed_dict['num_group'] = data_provider.get_group_num(user_id)
        feed_dict['field'] = self.get_secure_cookie("field").decode("utf-8")
        feed_dict['field_to_passed_test_cnt'] = get_user_field_to_test_cnt(user_id)
        feed_dict['field_to_total_test_cnt'] = get_field_to_test_cnt()
        import time
        start = time.time()
        feed_dict['field_to_tagged_problem_cnt'] = get_user_field_to_tagged_problem_cnt(user_id)
        feed_dict['faq'] = json.load(open(os.path.join(os.path.dirname(__file__), '../static/faq.json')))
        feed_dict['is_admin'] = self.check_authority(49999)
        feed_dict['is_blocked'] = data_provider.get_user_blocked(user_id)
        feed_dict['all_fields'] = business_config["visible_fields"]
        print(time.time()-start)

        #页面展示
        self.render("index.html", **feed_dict)


#登录页
class LoginHandler(RequestHandler):

    def get(self):
        action = self.get_argument("action", None)
        if action == "logout":
            #清楚session信息
            self.clear_cookie("username")
            self.clear_cookie("user_id")
            self.render("login.html", info_msg="注销成功!")
        elif action == "regsuccess":
            self.render("login.html", info_msg="注册成功!稍等半分钟再登陆，正在为您生成题库")
        else:
            self.render("login.html")

    #发送登录请求
    def post(self):
        try:
            name = self.get_argument("name")
            passwd = self.get_argument("pass")
        except tornado.web.MissingArgumentError:
            self.render("login.html", alert_msg="参数错误")
            return

        res, error_msg, user_id = data_provider.validate_user(name, passwd)
        if res is True:
            if user_id not in recommender.users:
                self.render("login.html", alert_msg="稍等半分钟再登陆，正在为您生成题库")
                return
            self.set_secure_cookie("username", name)
            self.set_secure_cookie("user_id", str(user_id))
            self.set_secure_cookie("launch_code", business_config['launch_code'])
            if self.get_secure_cookie("field") is None:
                self.set_secure_cookie("field", get_all_unfinished_fields()[0])
            self.redirect("/")
        else:
            self.render("login.html", alert_msg=error_msg)

class RegisterHandler(RequestHandler):
    def get(self):
        if len(recommender.users) < business_config["num_worker"]:
            self.render("register.html")
        else:
            self.render("login.html", alert_msg="抱歉，本次标注用户数目已满。请尝试注册其他标注。")

    #发送注册请求
    def post(self):
        if len(recommender.users) >= business_config["num_worker"]:
            self.render("login.html", alert_msg="抱歉，本次标注用户数目已满。请尝试注册其他标注。")
            return
        try:
            name = self.get_argument("username")
            passwd = self.get_argument("password")
            email = self.get_argument("email")
            student_id = self.get_argument("student_id")
            inviter_mail = self.get_argument("inviter_mail")
            recommend_list = self.get_arguments("buttons")
            if recommend_list == []:
                recommend_list = ['无']

            for arg in [name, passwd, email, student_id, inviter_mail]:
                if '"' in arg:
                    self.render("register.html", alert_msg="Potential malicious arguments. ")
                    return

        except tornado.web.MissingArgumentError:
            self.render("register.html", alert_msg="参数错误!")
            return

        if inviter_mail != "":
            cmd = """
              SELECT COUNT(*)
              FROM "users"
              WHERE email="{}"
            """.format(inviter_mail)
            result = data_provider.exesql(cmd)[0][0]
            if result == 0:
                self.render("register.html", alert_msg="该邀请人邮箱不存在，请重新确认。")
                return

        id_result = data_provider.exesql(f"SELECT id FROM users WHERE name = '{name}' and email = '{email}'")
        if len(id_result) > 0:
            self.render("register.html", alert_msg="请勿重复点击，稍等半分钟，正在为您生成题库")
            return
        cmd = """
          INSERT INTO users 
            (name, pass, email, student_id, authority, inviter_mail, good_list) 
          values ("{}", "{}", "{}", "{}", "{}", "{}", "{}")
        """.format(name, passwd, email, student_id, 0, inviter_mail, ' '.join(recommend_list))
        data_provider.exesql(cmd, False)
        self.redirect("/login?action=regsuccess")
        id_result = data_provider.exesql(f"SELECT id FROM users WHERE name = '{name}' and email = '{email}'")
        assert len(id_result) == 1, "What? duplicate/no user here? id_result is %s" % repr(id_result)
        user_id = id_result[0][0]
        assert user_id not in recommender.users, "user_id select failed"
        recommender.add_user(user_id)


#用于查询用户名是否已注册
class CheckNameHandler(RequestHandler):
    def post(self):
        name = self.get_argument("username")
        if re.match(r'^[\u4e00-\u9fa5_a-zA-Z0-9-]{4,16}$', name):
            res = data_provider.check_name(name)
        else:
            res = None
        self.write('{"status": "%s"}' % ("success" if res else "failed"))

#标注功能
class LabelHandler(BaseHandler):
    @tornado.web.authenticated
    @check_user_exists
    def get(self):
        feed_dict = {}
        
        username = tornado.escape.xhtml_escape(self.current_user)
        user_id = self.get_current_user_id()
        field = self.get_secure_cookie("field").decode("utf-8")
        if str(self.get_secure_cookie("launch_code"), encoding='utf-8') != \
                business_config['launch_code']:
            self.redirect('/login')
        else:
            feed_dict['username'] = username
            #0表示不是测试题
            feed_dict['test_type'] = 0
            feed_dict['user_total_tagged'] = recommender.users[user_id].answer_count + \
                                             recommender.users[user_id].diamond_count
            #dis为题面内容的json
            feed_dict['dis'] = get_problem(user_id, field)
            feed_dict['is_hard'] = False
            #没有符合条件的题返回None
            if len(feed_dict['dis']) == 0:
                feed_dict['dis'] = 'END'

            feed_dict['is_admin'] = self.check_authority(49999)
            self.render("label_sememe.html", **feed_dict)

class SkipHandler(BaseHandler):
    @tornado.web.authenticated
    @check_user_exists
    def post(self):
        pass


#接受答案
class SaveAnswerHandler(BaseHandler):
    @tornado.web.authenticated
    @check_user_exists
    def post(self):
        user_id = int(self.get_secure_cookie("user_id").decode())
        data = json.loads(self.request.body.decode("utf-8"))
        def data2answer():
            for d in data:
                if type(d['answer']) is str:
                    return d
        answer = data2answer()

        #保存答案并更新进度
        option = answer['answer']

        # 中止答题
        if not option:
            self.write("1")
            return

        group_id = answer['actualId']
        # [19723, 19587, 19276]
        cost_time = answer["cost_time"]
        if group_id > recommender.diamond_id_threshold:
            recommender.answer_diamond(user_id)
            group_id = recommender.max_question_id
            data_provider.db.insert('answer',
                                    {
                                        'user_id': user_id,
                                        'problem_group_id': group_id,
                                        'cost_time': cost_time,
                                        'answer': option,
                                        'is_diamond': 1 if answer['answer'].endswith(answer['hyponym']) else 2,
                                        'is_redundant': 0,
                                        'number': answer['number'],
                                        'round': answer['round'],
                                        'subtree_root': answer['hypernym']
                                    })

            self.write("1")
        else:
            #成功
            retcode = data_provider.save_answer(user_id, answer)
            if retcode == 1:
                data_provider.inc_group_num(user_id)
                self.write("1")

                # 保存答题记录
                recommender.answer(user_id, group_id, option, answer['round'])
                data_provider.db.insert('tagging_log',
                                        {
                                            'user_id': user_id,
                                            'problem_group_id': group_id,
                                            'type': "PROBLEM",
                                            'time': datetime.datetime.now()
                                        })

            #user repeat sending
            elif retcode == 2:
                self.write("2")
            else:
                #失败
                self.write("0")#调试页面，用于输出结果

class OutPutHandler(BaseHandler):
    def get(self):
        a = threading.Timer(1, data_provider.dump_problem())
        a.start()
        

#接受反馈
class FeedBackHandler(BaseHandler):
    @tornado.web.authenticated
    @check_user_exists
    def post(self):
        user_id = int(self.get_secure_cookie("user_id").decode())
        data = json.loads(self.request.body)
        data['user_id'] = user_id
        data_provider.save_feedback(data)
        self.write('1')

#重置测试功能
class ResetTestHandler(BaseHandler):
    @tornado.web.authenticated
    @check_user_exists
    def get(self):
        user_id = int(self.get_secure_cookie("user_id").decode("utf-8"))
        data_provider.reset_test(user_id)
        self.write('1')

#测试题功能
class TestHandler(BaseHandler):

    @tornado.web.authenticated
    @check_user_exists
    def get(self):
        user_id = int(self.get_secure_cookie("user_id").decode("utf-8"))
        field = self.get_secure_cookie("field").decode("utf-8")
        
        feed_dict = {}
        #provide to front-end
        feed_dict['test_type'] = 1
        feed_dict['user_total_tagged'] = 0
        feed_dict['dis'] = get_test_problem(user_id, field)
        feed_dict['is_hard'] = False
        #没有符合条件的题返回None
        if len(feed_dict['dis']) == 0:
            feed_dict['dis'] = 'END'

        feed_dict['is_admin'] = self.check_authority(49999)
        self.render("label_sememe.html", **feed_dict)

    @check_user_exists
    def post(self):
        user_id = int(self.get_secure_cookie("user_id").decode("utf-8"))
        data = json.loads(self.request.body.decode("utf-8"))
        err = []
        for i in range(len(data)):
            item = data[i]
            ground_truth = data_provider.get_test_answer(item[u'actualId'])
            if item['answer'] != ground_truth:
                err.append(i)
        test_process = data_provider.get_pass_test(user_id)
        if len(err) == 0:
            data_provider.inc_pass_test(user_id, test_process + 1)
            if test_process + 1 == data_provider.get_test_group_count():
                self.write('2 0 0')
                return    
            self.write('1 0 0')

            problem_group_id = data[0]['group_id']
            data_provider.db.insert('tagging_log',
                                    {
                                        'user_id': user_id,
                                        'problem_group_id': problem_group_id,
                                        'type': "TEST",
                                        'time': datetime.datetime.now()
                                    })

        else:
            self.write('0 ' + str(len(data)-len(err)) +' '+ str(test_process))
            for item in err:
                self.write(" " + str(item))

#查看用户标注情况
class UserStatusHandler(BaseHandler):

    column_names = [u"ID", u"用户名", u"通过测试", u"标注数量", u"黄金标注", u"正确黄金标注", u"黄金正确率", u"钻石标注", u"钻石正确率", u"无视", u"封禁"]

    def render_table(self):

        users = data_provider.exesql("""
        SELECT id, name, pass_test, group_num, ignored, blocked from users
      """)

        gold_problems = data_provider.exesql("""
        SELECT user_id, answer, gold_answer FROM answer INNER JOIN problem ON problem.problem_group_id = answer.problem_group_id
        WHERE gold_answer <> ''
      """)

        user_to_gold_answer_count = {user_id: 0 for user_id, _, _, _, _, _ in users}
        user_to_gold_answer_correct = {user_id: 0 for user_id, _, _, _, _, _ in users}

        for user_id, answer, gold_answer in gold_problems:
            if gold_answer:
                user_to_gold_answer_count[user_id] += 1
                if answer == gold_answer:
                    user_to_gold_answer_correct[user_id] += 1

        users_data = []

        for user_id, name, pass_test, group_num, ignored, blocked in users:
            user_hyperlink = '<a href="/user_tagging/%s">%s</a>' % (user_id, name)

            if ignored == 0:
                ignore_link = '<a href="/user_status?set=ignored&id=%s&value=1">无视</a>' % user_id
            else:
                ignore_link = '<a href="/user_status?set=ignored&id=%s&value=0">解除</a>' % user_id

            if blocked == 0:
                block_link = '<a href="/user_status?set=blocked&id=%s&value=1">封禁</a>' % user_id
            else:
                block_link = '<a href="/user_status?set=blocked&id=%s&value=0">解封</a>' % user_id

            diamond_right = data_provider.exesql(f"SELECT count(*) FROM answer WHERE user_id = {user_id} and is_diamond = 1")
            diamond_wrong = data_provider.exesql(f"SELECT count(*) FROM answer WHERE user_id = {user_id} and is_diamond = 2")
            diamond_right = diamond_right[0][0]
            diamond_wrong = diamond_wrong[0][0]
            diamond_total = diamond_right + diamond_wrong
            diamond_accuracy = (diamond_right / diamond_total) if diamond_total else 1.0
            users_data.append((
                user_id,
                user_hyperlink,
                pass_test,
                group_num,
                user_to_gold_answer_count[user_id],
                user_to_gold_answer_correct[user_id],
                0 if user_to_gold_answer_count[user_id] == 0
                else 1.0 * user_to_gold_answer_correct[user_id] / user_to_gold_answer_count[user_id],
                diamond_total,
                diamond_accuracy,
                ignore_link.replace("&", "&amp;"),
                block_link.replace("&", "&amp;"),
            ))

        management_info = """
+ 用户管理后台：
  + 点击用户名：查看该用户的标注情况。
  + 封禁：该用户被封禁期间将无法进行标注任务，且该用户的标注视为无效标注。
  + 无视：该用户的标注被认为是无效标注，但该用户依旧可以继续标注。
        """

        field_sta_info = []

        field_sta_template = """
+ %s: 总条目数：%d, 已经标注次数：%d, 有效标注次数：%d, 标注完成条目数: %d
        """

        tags, valid_tags, finished_problem_count, all_problem_count = data_provider.count_tagged_problems()
        field_sta_info.append(field_sta_template % ("总计", all_problem_count, tags, valid_tags, finished_problem_count))

        for field in get_all_fields():
            tags, valid_tags, finished_problem_count, all_problem_count = data_provider.count_tagged_problems(field)
            field_sta_info.append(field_sta_template % (field, all_problem_count, tags, valid_tags, finished_problem_count))


        info = "\n".join([management_info] + field_sta_info)

        feed_dict = {
            "column_names": self.column_names,
            "rows": users_data,
            "info": info,
        }

        feed_dict['is_admin'] = self.check_authority(49999)
        self.render("display_table.html", **feed_dict)

    def action(self):
        set = self.get_argument("set", default=None)
        if set:
            try:
                user_id = int(self.get_argument("id"))
                value = int(self.get_argument("value"))
                if set == "blocked":
                    sql = """
                        UPDATE users set blocked = %d where id = %d
                    """ % (value, user_id)
                    data_provider.exesql(sql, False)
                    user = recommender.users[user_id]
                    if value == 1:
                        # user.ignore_me()
                        user.blocked = True
                    if value == 0:
                        # user.release_me()
                        user.blocked = False
                    print(sql)
                elif set == "ignored":
                    sql = """
                        UPDATE users set ignored = %d where id = %d
                    """ % (value, user_id)
                    data_provider.exesql(sql, False)
                    user = recommender.users[user_id]
                    if value == 1:
                        user.ignore_me()
                    if value == 0:
                        user.release_me()
                    print(sql)
                else:
                    raise ValueError("Invalid parameter 'set'. ")
                
            except ValueError as e:
                self.set_status(400)
                return
                
    
    @tornado.web.authenticated
    @check_user_authority(49999)
    #@check_user_authority(0)
    def get(self):
        self.action()
        self.render_table()

#查看某一用户的所有标注
class UserTaggingHandler(BaseHandler):

    column_names = [u"ID", u"用户名", u"题目", u"答案", u"黄金答案", u"正确黄金标注"]

    @tornado.web.authenticated
    @check_user_authority(49999)
    def get(self, tg_user_id):

        user_names = data_provider.exesql("""
          SELECT name from users WHERE id='%s'
        """ % tg_user_id)

        if len(user_names) == 0:
            self.redirect("/")
            return

        tg_user_name = user_names[0][0]

        problems = data_provider.exesql("""
            SELECT user_id, answer, hyponym, gold_answer FROM answer INNER JOIN problem ON problem.problem_group_id = answer.problem_group_id
        """)

        data = []
        for user_id, answer, hyponym, gold_answer in problems:
            if not gold_answer:
                gold_answer = "无"
                gold_correct = "无"
            else:
                gold_correct = '是' if answer == gold_answer else '否'

            data.append((tg_user_id, tg_user_name, hyponym, answer, gold_answer, gold_correct))

        info = ""

        feed_dict = {
            "column_names": self.column_names,
            "rows": data,
            "info": info,
        }

        feed_dict['is_admin'] = self.check_authority(49999)
        self.render("display_table.html", **feed_dict)

# 查看标注日志
class TaggingLog(BaseHandler):

    column_names = ["序", "用户 ID", "用户名", "问题组 ID", "时间"]

    @tornado.web.authenticated
    @check_user_authority(49999)
    def get(self):
        data = data_provider.exesql("""
          SELECT tagging_log.id, tagging_log.user_id, users.name, tagging_log.problem_group_id, tagging_log.time
          FROM "tagging_log" join "users" on tagging_log.user_id == users.id
          ORDER BY tagging_log.id DESC
        """)

        data = [(len(data) - tagging_log_id,
                 user_id,
                 '<a href="/user_tagging/%s">%s</a>' % (user_id, username),
                 problem_group_id,
                 t) for tagging_log_id, user_id, username, problem_group_id, t in data]

        info = """
        
        """

        feed_dict = {
            "column_names": self.column_names,
            "rows": data,
            "info": info
        }

        feed_dict['is_admin'] = self.check_authority(49999)
        self.render("display_table.html", **feed_dict)

# 报酬信息录入
class PayInfo(BaseHandler):

    def get_user_pay_info(self):
        cmd = """
          SELECT users.real_name,
                 users.id_card,
                 users.bank_name,
                 users.bank_id,
                 users.working_site,
                 users.telephone
          FROM users
          WHERE users.id = "%s";
        """ % self.get_current_user_id()

        data = data_provider.exesql(cmd)

        real_name, id_card, bank_name, bank_id, working_site, telephone = data[0]

        return {
            "real_name": real_name,
            "id_card": id_card,
            "bank_name": bank_name,
            "bank_id": bank_id,
            "working_site": working_site,
            "telephone": telephone,
        }

    def get_user_income_info(self):
        user_id = self.get_current_user_id()
        user_tagging_count = get_user_tagging_count(user_id)

        tagging_reward = user_tagging_count * business_config["problem_reward"]
        invitation_reward = get_user_invitations(user_id) * business_config["invitation_reward"]
        user_paid = data_provider.exesql("""
            SELECT paid FROM users WHERE users.id = "{}"
        """.format(user_id))[0][0]

        return {
            "total_reward_yuan": fen2yuan(tagging_reward + invitation_reward),
            "user_paid_yuan": fen2yuan(user_paid),
            "user_tagging_count": user_tagging_count,
            "problem_reward_yuan": fen2yuan(business_config["problem_reward"]),
            "invitation_reward_yuan": fen2yuan(invitation_reward)
        }


    @tornado.web.authenticated
    @check_user_exists
    def get(self):
      self.render("pay_info.html", **self.get_user_pay_info(), **self.get_user_income_info())

    @tornado.web.authenticated
    @check_user_exists
    def post(self):
        user_input = {
            "real_name": None,
            "id_card": None,
            "bank_name": None,
            "bank_id": None,
            "working_site": None,
            "telephone": None,
        }

        try:
            password = self.get_argument("password")
            real_name = self.get_argument("real_name")
            id_card = self.get_argument("id_card")
            bank_name = self.get_argument("bank_name")
            bank_id = self.get_argument("bank_id")
            working_site = self.get_argument("working_site")
            telephone = self.get_argument("telephone")

            user_input = {
                "real_name": real_name,
                "id_card": id_card,
                "bank_name": bank_name,
                "bank_id": bank_id,
                "working_site": working_site,
                "telephone": telephone,
            }

            for arg in [password, real_name, bank_name, bank_id, working_site, telephone]:
                trusted_arg_reg = r"^[ \u4E00-\u9FA5a-zA-Z\-.,0-9·]*$"
                if re.match(trusted_arg_reg, arg) is None:
                    raise ValueError("Potential malicious arguments! ")

        except tornado.web.MissingArgumentError:
            self.render("pay_info.html", alert_msg="参数错误!", **user_input, **self.get_user_income_info())
            return

        except ValueError as e:
            self.render("pay_info.html", alert_msg=e, **user_input, **self.get_user_income_info())
            return

        user_id = self.get_current_user_id()
        cmd = """
        SELECT users.name,
               users.pass
        FROM users
        WHERE users.id = "%s";
        """ % user_id

        user_name, hashed_password = data_provider.exesql(cmd)[0]
        concated_password = "%s;%s" % (user_name, password)

        md5 = hashlib.md5()
        md5.update(concated_password.encode("utf-8"))
        hashed_concated_password = md5.hexdigest()

        if hashed_concated_password != hashed_password:
            self.render("pay_info.html",
                        alert_msg="输入密码有误，如果您忘记密码，请联系管理员。",
                        **user_input,
                        **self.get_user_income_info())
            return

        cmd = """
        UPDATE users SET
            real_name = "{}",
            id_card = "{}",
            bank_name = "{}",
            bank_id = "{}",
            working_site = "{}",
            telephone = "{}"
        WHERE users.id = "{}"
        """.format(real_name.strip(),
               id_card.strip(),
               bank_name.strip(),
               bank_id.strip(),
               working_site.strip(),
               telephone.strip(),
               user_id)

        data_provider.exesql(cmd, select=False)

        self.redirect("/")

# 选择领域
class SelectField(BaseHandler):

    @tornado.web.authenticated
    @check_user_exists
    def post(self):
        data = json.loads(self.request.body.decode("utf-8"))
        self.set_secure_cookie("field", data["field"])

class PayManage(BaseHandler):

    @tornado.web.authenticated
    @check_user_authority(49999)
    def get(self):
        feed_dict = {
            "is_admin": self.check_authority(49999)
        }
        self.render("pay_manage.html", **feed_dict)

# 读写报酬报表
class PayTable(BaseHandler):

    all_columns = ["用户ID", "用户名", "邮箱", "清华学号", "真实姓名",
                   "身份证", "银行", "银行账号", "工作地点", "用户电话",
                   "标注数", "已支付", "已封禁", "已屏蔽"]

    @tornado.web.authenticated
    @check_user_authority(49999)
    def get(self):
        cmd = """
        SELECT tagging_log.user_id, 
               users.name,
               users.email,
               users.student_id,
               users.real_name,
               users.id_card,
               users.bank_name,
               users.bank_id,
               users.working_site,
               users.telephone,
               COUNT(DISTINCT(tagging_log.problem_group_id)),
               users.paid,
               users.blocked,
               users.ignored 
        FROM tagging_log JOIN users ON tagging_log.user_id = users.id
        WHERE tagging_log.type = "PROBLEM"
        GROUP BY tagging_log.user_id
        """

        result = data_provider.exesql(cmd)

        df = pd.DataFrame(result, columns=self.all_columns)

        user_id_to_invitations = get_all_user_invitations()

        invited_tags = pd.Series([
                           user_id_to_invitations[user_id]
                           if user_id in user_id_to_invitations and not recommender.users[user_id].ignored
                           else 0
                           for user_id in df["用户ID"]
                       ])

        hard_problem_count = recommender.hard_problem_count()
        hard_problem_count = pd.DataFrame([hard_problem_count[u] for u in df['用户ID']])

        df["邀请标注"] = invited_tags
        df["已支付"] = df["已支付"] / 100

        df["应支付"] = (business_config["problem_reward"] * df["标注数"] / 100 + \
                        business_config["invitation_reward"] * invited_tags / 100 + \
                            business_config["hard_problem_additional_reward"] * hard_problem_count.transpose() / 100).transpose()

        with tempfile.NamedTemporaryFile() as f:
            writer = pd.ExcelWriter(f.name, engine="openpyxl")
            df.to_excel(writer)
            writer.save()

            self.set_header('Content-Type', 'application/octet-stream')
            self.set_header('Content-Disposition', 'attachment; filename=THUKEG_Pay_Report_%s.xlsx' % time.strftime("%Y%m%d"))

            download = open(f.name, "rb")
            while True:
                data = download.read(4096)
                if not data:
                    break
                self.write(data)

            self.finish()

    #@tornado.web.authenticated
    #@check_user_authority(49999)
    def post(self):
        print(self.request.arguments)
        file_content = self.request.files['excel'][0]['body']

        try:
            df = pd.read_excel(io.BytesIO(file_content))
            updates = 0

            error = "OK"
            info = ""

            for user_id, paid in df[["用户ID", "已支付"]].values:
                user_id = int(user_id)
                paid = yuan2fen(paid)
                if not data_provider.exists_user(user_id):
                    raise ValueError("用户ID不存在：%d" % user_id)
                cmd = """
                UPDATE users set
                    paid = "{}"
                WHERE users.id = "{}"
                """.format(paid, user_id)

                data_provider.exesql(cmd, select=False)
                updates += 1

            info = "成功更新 {} 位用户的数据。".format(updates)
        except KeyError as e:
            error = str(type(e))
            info = str(e)
        except ValueError as e:
            error = str(type(e))
            info = str(e)
        except xlrd.biffh.XLRDError as e:
            error = str(type(e))
            info = "读取 Excel 文件发生错误，请确认格式为 XLSX。"

        self.finish({
            "error": error,
            "info": info
        })

# 下载标注结果
class DownloadEffectiveTags(BaseHandler):

    @tornado.web.authenticated
    @check_user_authority(49999)
    def get(self):
        cmd = """
        SELECT id FROM "users"
        WHERE blocked = 1 OR ignored = 1
        """

        blacklisted_users = set([x[0] for x in data_provider.exesql(cmd)])

        print(blacklisted_users)

        cmd = """
        SELECT hyponym, hypernym, user_ids, answers, field, problem_group_id
		FROM problem 
		WHERE LENGTH(user_ids) > 0 AND gold_answer == -1
        """

        rows = data_provider.exesql(cmd)

        def groupby(iter, key_getter, grouping_handler=None):
            if type(key_getter) == str:
                row_key = key_getter
                key_getter = lambda x: x[row_key]

            r = {}
            for row in iter:
                key = key_getter(row)
                if key in r:
                    r[key].append(row)
                else:
                    r[key] = [row]

            if grouping_handler:
                for k, v in r.items():
                    r[k] = grouping_handler(v)

            return r
        hyponym_to_rows = groupby(rows, lambda x: x[-1])

        self.set_header('Content-Type', 'application/octet-stream')
        self.set_header('Content-Disposition',
                        'attachment; filename=THUKEG_Effective_Tags_%s.json' % time.strftime("%Y%m%d"))

        for problem_group_id, rows in hyponym_to_rows.items():
            level_vote = [0] * len(rows)
            hypernym = "UNK"
            hyponym = "UNK"
            field = "UNK"
            for row in rows:
                hyponym, hypernym, user_ids, answers, field, _ = row
                for user_id, answer in zip(user_ids[0:-1].split(","), answers[0:-1].split(",")):
                    user_id, answer = int(user_id), int(answer)
                    if user_id in blacklisted_users:
                        continue
                    if answer == 1:
                        level = hypernym.count("/")
                        level_vote[level] += 1

            self.write(json.dumps({
                "concept": hyponym,
                "field": field,
                "route": hypernym.split("/"),
                "votes": level_vote,
            }, ensure_ascii=False) + "\n")

        self.finish()
