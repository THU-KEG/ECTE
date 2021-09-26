#coding:utf-8
#/usr/bin/env python3
#处理数据库增删改查
#代码SQL语句过多，未防范SQL注入攻击
import sqlite3
import logging
try:
    from handlers.hownetFunction import *
except ModuleNotFoundError:
    from hownetFunction import *

class DB:
    # consts
    ALL_KEYS = 0

    def __init__(self, path):
        self.path = path
        try:
            conn = sqlite3.connect(path)
            conn.close()
        except sqlite3.Error:
            raise ValueError("Invalid database at %s" % path)
        logging.info("Connected to database.")

        # initialize db
        tables = self._execute('SELECT tbl_name FROM sqlite_master WHERE type=?', ['table'], True)
        tables = set([x[0] for x in tables])

    def _create_table(self, name, keys):
        cmd = 'create table %s (id integer primary key not null, %s);' % (name, ','.join(keys))
        self._execute(cmd)

    def _unpack_params_dict(self, params_dict, delimeter=' and '):
        cmd = delimeter.join(['%s=?' % k for k in params_dict])
        return cmd, params_dict.values()

    def _execute(self, cmd, params=None, is_select=False):
        if params is None: params = []
        if not isinstance(params, list): params = list(params)
        conn = sqlite3.connect(self.path)
        cursor = conn.cursor()
        logging.debug(cmd + ' ' + str(params))
        cursor.execute(cmd, params)
        if is_select:
            ret = cursor.fetchall()
        else:
            ret = cursor.rowcount
            conn.commit()
        cursor.close()
        conn.close()
        logging.debug(str(ret))
        return ret

    def select(self, table, keys=ALL_KEYS, conditions=None, orderby=None, asc_desc='asc'):
        params = []
        if keys == DB.ALL_KEYS:
            keys_cmd = '*'
        else:
            keys_cmd = ','.join(keys)
        cmd = 'select %s from %s' % (keys_cmd, table)
        if conditions:
            cond_cmd, cond_params = self._unpack_params_dict(conditions)
            cmd += ' where %s' % cond_cmd
            params = cond_params
        if orderby:
            cmd += ' order by %s %s' % (','.join(orderby), asc_desc)
        return self._execute(cmd, params, True)

    def update(self, table, updates, conditions):
        updates_cmd, updates_params = self._unpack_params_dict(updates, delimeter=', ')
        cond_cmd, cond_params = self._unpack_params_dict(conditions)
        cmd = 'update %s set %s where %s' % (table, updates_cmd, cond_cmd)
        params = list(updates_params) + list(cond_params)
        self._execute(cmd, params)

    def insert(self, table, params):
        keys = ','.join(params.keys())
        placeholder = ','.join(['?'] * len(params))
        cmd = 'insert into %s (%s) values (%s)' % (table, keys, placeholder)
        self._execute(cmd, params.values())

    def delete(self, table, conditions):
        cond_cmd, cond_params = self._unpack_params_dict(conditions)
        cmd = 'delete from %s where %s' % (table, cond_cmd)
        self._execute(cmd, cond_params)

    #以上为增删改查标准函数，以下为完成特殊功能的特点函数
    def get_test_answer(self, id):
        cmd = 'select answer from test WHERE id = %d'%(id)
        return self._execute(cmd, [], True)[0][0]

    def select_test_problem(self, test_process):
        cmd = 'select * from test WHERE problem_group_id = %d'%(test_process)
        return self._execute(cmd, [], True)                     

    def get_user_progress(self, user_id):        
        cmd = 'select progress from users WHERE id = %d'%(user_id)
        user_progress = int(self._execute(cmd, [], True)[0][0])
        return user_progress

    def get_id(self, name):
        conditions = {}
        conditions['name'] = '= %s'%(name)
        return self.select('users', ['id'], conditions)

    def select_problem(self, user_progress, user_id):
        #找出大于进度的，最小的未完成的那一组
        cmd = 'select * from problem WHERE problem_group_id = (select min(problem_group_id) from problem Where isdone = 0 AND problem_group_id > %d)'%(user_progress)
        return self._execute(cmd, [], True)

    def get_all_blocked_or_ignored_users(self):
        return self._execute("""
            SELECT id, blocked, ignored FROM "users"
            WHERE blocked = 1 OR ignored = 1
        """, [], True)

    def get_all_sememe(self, babelnet_synset_id):
        cmd = 'select DISTINCT sememe_name, problem.sememe_id from problem join sememe \
        on problem.sememe_id = sememe.sememe_id where problem.babelnet_synset_id = "%s"'%(babelnet_synset_id)
        return self._execute(cmd, [], True)


    #用于debug
    def test(self):
        cmd = 'select name from sqlite_master where type= %s order by name'%('\'table\'')
        print(self._execute(cmd , [], True))
        print(self.select(table = 'problem'))

    def get_sememe_data(self, sememe_id, sense_num = 5):
        cmd = 'select sememe_name, sememe_id from sememe WHERE sememe_id = %d LIMIT %d'%(sememe_id, sense_num)
        return self._execute(cmd, [], True)

    def get_tree(self, sense_id):
        cmd = 'select distinct tree from hownet_sense WHERE hownet_sense_id = %d'%(sense_id)
        return self._execute(cmd, [], True)

    def get_tree_by_sememe_id(self, sememe_id):
        cmd = 'select distinct tree from sememe,hownet_sense WHERE sememe.hownet_sense_id = hownet_sense.hownet_sense_id AND sememe_id = %s ORDER BY word_count DESC LIMIT 10'%(sememe_id)
        return self._execute(cmd, [], True)

    def get_synset_data(self, babelnet_synset_id):
        cmd = 'select display_content from babelnet_synset WHERE babelnet_synset_id = "%s"'%(babelnet_synset_id)
        return self._execute(cmd, [], True)

    def check_passed_test(self, user_id, table = 'users'):
        cmd = 'select %s from %s WHERE id = %s' %('pass_test',table, user_id)
        
        if(int(self._execute(cmd, [], True)[0][0]) >= self.get_test_group_count()):
            return True
        else:
            return False

    def dump_table(self,table_name):
        cmd = 'select * from ' + table_name
        return self._execute(cmd, [], True)

    #执行sql语句
    def exesql(self, sql, params=None, select=True):
        if not params:
            params = []
        return self._execute(sql, params, select)

    def count(self, table_name):
        return len(self._execute("SELECT * FROM " + table_name, [], True))

    def get_test_group_count(self):
        return len(self._execute("SELECT * FROM test GROUP BY problem_group_id", [], True))

    #用于标注完成后生成最终结果文件
    def select_final_result(self):
        cmd = 'select * from problem'
        res = self._execute(cmd, [], True)
        output = []
        for item in res:
            output_item = {}
            output_item['problem_id'] = item[0]
            sememe_id = item[2]
            babel_id = item[3]
            output_item['group_id'] = item[4]
            output_item['answers'] = item[6]
            output_item['cost_time'] = item[7]
            output_item['user_id'] = item[5]
            output_item['babel_id'] = babel_id
            output_item['sememe'] = self.get_sememe_data(sememe_id)[0][0]
            output_item['synset'] = self.get_synset_data(babel_id)[0][0]
            output.append(output_item)
        return output



