import pytest

from moto.server import ThreadedMotoServer

_proxy_bypass = {
  "http": None,
  "https": None,
}


# TODO this in theory can run for all tests not 1 per service
def start_service(host, port) -> ThreadedMotoServer:
    server = ThreadedMotoServer(ip_address=host, port=port, verbose=False)
    server.start()
    return server


def stop_process(server: ThreadedMotoServer):
    server.stop()


@pytest.fixture(scope="session")
def moto_server():
    host = "localhost"
    port = 5001
    url = "http://{host}:{port}".format(host=host, port=port)
    process = start_service(host, port)
    yield url
    stop_process(process)
