=========
Changelog
=========

The format is based on `Keep a Changelog: https://keepachangelog.com/en/1.0.0/`,
and this project adheres to `Semantic Versioning: https://semver.org/spec/v2.0.0.html`

Unreleased
----------

Added
^^^^^

Changed
^^^^^^^

Deprecated
^^^^^^^^^^

Removed
^^^^^^^

Fixed
^^^^^

Security
^^^^^^^^

v0.1.2 (2018-11-22)
-------------------

Changed
^^^^^^^
* Callback handling. Apparently it got object referencing problems when running
  multiple threads using and instance of the module class.

Fixed
^^^^^
* Small bug when a UDP message is not received we parsed and empty response.


v0.1.1 (2018-11-21)
-------------------

Added
^^^^^
* Added functionality to read data from UDP sockets.
* Added interface for socket.recvfrom() to socket class.
* Small wait time on writes not to block interface.
* Current RAT information
* Possibility to set socket in listening mode


Changed
^^^^^^^
* update_radio_statistics is now a public function
* callback registration process

v0.1.0  (2018-10-24)
--------------------

Added
^^^^^
* Arg to specify if the module is roaming or when connecting specify if roaming so that we know what to expect in the connection status.
* capture_urc flag to _at_command(). So that it is possible to collect the URCs before the OK response.
* Added the UbloxSocket and UDPSocket classes to be able to handle sockets independent from module.

Changed
^^^^^^^
* Removed operators name and map. Now you need to specify the operator with its MNO_ID. Swedish Telia is for example 24001.
* Renamed eps_reg_status to registration_status. Even if it does not follow the naming in the ublox manual it is clearer in the code what it is.
* create_socket now returns a UbloxSocket subclass.


v0.0.2
------

Added
^^^^^
* Better support for R412.
* errors for AT commands and module errors will throw python exceptions.
* setting bands on r4 modules.


Changed
^^^^^^^
* Renamed function to set up the module from init to setup to have a clearer API.
* Improvement of api and made methods common.

v0.0.1
------
First version. Support for SARA-N211 and initial support for SARA-R412