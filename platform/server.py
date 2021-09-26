#!/usr/bin/env Python
# coding=utf-8
from __future__ import print_function
import tornado.ioloop
import tornado.options
import tornado.httpserver
import logging
from application import application
from tornado.options import define, options
from handlers import main_handler, ranking_handler
import handlers.data
import json
from handlers.recommender import Recommender


define("port", default=8200, type=int, help="Port to listen.")
define("static", default="./static/", help="Entry point of static files.")
define("debug", default=False, help="Run in debug mode.")
define("num_inst_per_group", default=20, type=int, help="Number of instances per group.")
define("db", default="./static/mkg_tagging.db", type=str, help="Path to the sqlite database.")
define("bc", default="./business_config.json", type=str, help="Path to business_config.json.")





def main():
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(options.port)
    main_handler.business_config = json.load(open(options.bc, mode="r", encoding="utf-8"))
    db_name = options.db if options.db else main_handler.business_config["db_name"]
    main_handler.data_provider = handlers.data.DataProvider(db_name)
    main_handler.recommender = Recommender(main_handler.data_provider, main_handler.business_config['instance_filename'])
    # import subprocess
    # for i in range(100):
    #     subprocess.run(['python3.6', 'static/answer3.py', '/tmp/a.db', '1', '100', '0.8'])
    #     main_handler.data_provider = handlers.data.DataProvider(main_handler.business_config["db_name"])
    #     main_handler.recommender = Recommender(main_handler.data_provider)
    ranking_handler.recommender = main_handler.recommender

    print("Development server is running at http://127.0.0.1:%s" % options.port)
    print("Quit the server with Control-C")


    logging.basicConfig(level=logging.DEBUG, filename='main.log')
    logging.debug("Now in debug mode.")
    logging.info("Tornado server is now running. Listening on port %d", options.port)

    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":

    main()

