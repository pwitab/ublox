=================
Using the library
=================

Supported Modules
=================

We have tested the library agains the following module:

* SARA N211
* SARA R410
* SARA R412

Since Ublox has the same AT commands for alot of their modules it might work on
other modules as well.

Creating a module
=================

You need to connect the module over a serial line and declare the module in
the program using the serial port.

For development we have used Sodaq boards where an Arduino is controlling the
module. By using a small passthrough program we can connect the serial interface
from the board to our computer via the arduino. The Arduino is also responsible
for setting the power pins to the module so it starts.

.. code-block:: python

    # Creating a module
    module = SaraR4Module(serial_port='/dev/tty.usbmodem14111')


Configure module
================

We are running tests in Sweden and have defined settings to configure the module
to work for operators in Sweden. You can set the module up using the .setup()
method or use lower API method ._at_action() to set the module up exactly as you
want.

.. code-block:: python

    module.setup()
    # or
    module._at_action('AT+CFUN=1')

There are also methods that wrap common at actions that are documented on the
module class.

Connect the module to a network
===============================

When connecting it is important to know if you operator is running in home
network or in roaming network. This will give different response when waiting
for the connection signal.

You use the numerical ID of you operator (MNO) to connect. In Sweden Telia is
24001 and Tre is 24002.

.. code-block:: python

    module.connect(operator=24001, roaming=True)


Sending Data
============

When you want to send data you need to create a socket on the module. This is
represented in the library as an object that looks and behaves like a normal
python socket.

.. code-block:: python

    sock = module.create_socket(socket_type='UDP', port=1337)
    sock.sendto(b'mytestdata', ('195.34.89.241', 7))
    # when you don't need the socket you can close it.
    sock.close()


Monitor radio environment
=========================

On of the things we are using the library for is to monitor coverage and the
radio environment of NB-IoT.
You can use the .update_radio_statistics() to get new values from the module
and access them on the module object.

.. code-block:: python

    module.update_radio_statistics()
    print(module.radio_rsrq)
    print(module.radio_rsrp)


.. note::

    Different modules support different statistics values.
