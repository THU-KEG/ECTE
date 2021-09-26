#!/usr/bin/env Python
# coding=utf-8
"""
the url structure of website
"""

import sys     #utf-8，兼容汉字
import tornado
from tornado.options import define, options

from handlers.main_handler import *
from handlers.ranking_handler import RankingHandler

url = [
  (r'/', MainHandler),
  (r'/label', LabelHandler),
  (r'/login', LoginHandler),
  (r'/register', RegisterHandler),
  (r'/check_name', CheckNameHandler),
  (r'/answer', SaveAnswerHandler),
  (r'/skip', SkipHandler),
  (r'/outputt', OutPutHandler),
  (r'/feedback', FeedBackHandler),
  (r'/test', TestHandler),
  (r'/resettest', ResetTestHandler),
  (r'/user_status', UserStatusHandler),
  (r'/user_tagging/(.*)', UserTaggingHandler),
  (r'/tagging_log', TaggingLog),
  (r'/pay_info', PayInfo),
  (r'/select_field', SelectField),
  (r'/pay_table', PayTable),
  (r'/pay_manage', PayManage),
  (r'/download_effective_tags', DownloadEffectiveTags),

  (r'/ranking', RankingHandler)
]