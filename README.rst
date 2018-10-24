======
U-blox
======

Python library for U-blox cellular modules.

Installation
============

Python version supported: 3.6+

.. code-block::

    pip install ublox


About
=====

The ublox library gives a python interface to AT Commands via serial interface
to Ublox modules. This can used for testing and profiling of modules and
technologies or you might want to hook up a small python program on an embedded
device to send data over, for example, NB-IoT.

Supported Modules
=================

* SARA-N211
* SARA-R410
* SARA-R412

Example Use:
============

.. code-block::

    module = SaraR4Module(serial_port='/dev/tty.usbmodem14111')
    module.setup()
    module.connect(operator=24001)
    sock = module.create_socket()
    sock.sendto(b'Message To Echo Server', ('195.34.89.241', 7))
    sock.close()

Development
===========

The library is currently used for testing infrastructure in Sweden. If you find
problems in your country please open an issue so we can make the library as
general as possible.

If you have special need there is always the possibility to used the lower
level API for AT Commands via ._at_command()

If you have use-cases that could be solved with more options on functions, make
the change yourself and open a pull request or open an issue.





