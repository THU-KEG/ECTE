# coding:utf-8
# 一些功能函数
import hashlib
# from nltk.metrics.agreement import AnnotationTask as AnnoTask


#对密码进行md5
def md5_passwd(str, salt='123485'):
    str = str + salt
    md = hashlib.md5()
    md.update(str.encode())
    res = md.hexdigest()
    return res
