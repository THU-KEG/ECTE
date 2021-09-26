#!/usr/bin/env python3
import os, sys, time
import signal
import logging
from functools import partial

import tornado
from tornado.options import define, options


from url import url

MAX_WAIT_SECONDS_BEFORE_SHUTDOWN = 3

settings = dict(
    cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
    login_url= "/login",
    template_path = os.path.join(os.path.dirname(__file__), "templates"),
	static_path = os.path.join(os.path.dirname(__file__), "static"),
    xsrf_cookies=False,
)

application = tornado.web.Application(
    handlers = url,
    **settings
    )
'''
def sig_handler(server, sig, frame):
    io_loop = tornado.ioloop.IOLoop.instance()

    # pylint: disable=E1101
    def stop_loop(deadline):
        io_loop.stop()
        logging.info('Shutdown finally')

    def shutdown():
        logging.info('Stopping http server')
        server.stop()
        logging.info('Will shutdown in %s seconds ...',
                     MAX_WAIT_SECONDS_BEFORE_SHUTDOWN)
        stop_loop(time.time() + MAX_WAIT_SECONDS_BEFORE_SHUTDOWN)

    logging.warning('Caught signal: %s', sig)
    io_loop.add_callback_from_signal(shutdown)
'''

'''
def main():
    app = Application()

    server = tornado.httpserver.HTTPServer(app, xheaders=True)
    server.listen(options.port)

    signal.signal(signal.SIGTERM, partial(sig_handler, server))
    signal.signal(signal.SIGINT, partial(sig_handler, server))
    
    if options.debug: 
        logging.getLogger().setLevel(logging.DEBUG)
    logging.debug("Now in debug mode.")
    logging.info("Tornado server is now running. Listening on port %d", options.port)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
    main()
'''