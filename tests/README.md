# Testing networkmgr modules

Testing networkmgr modules with pytest

1. Create a virtual environment using python 3.8
2. Activate the venv
3. Install pytest and pytest coverage
4. Execute pip list to verify your environment.

```bash
python3.8 -m venv venv38

source venv38/bin/activate

pip install pytest pytest-cov

networkmgr-fork/tests on  unit_tests [!?] via 🐍 v3.8.12 (venv38) 
❯ pip list
Package    Version
---------- -------
attrs      21.2.0
coverage   6.2
iniconfig  1.1.1
packaging  21.3
pip        21.3.1
pluggy     1.0.0
py         1.11.0
pyparsing  3.0.6
pytest     6.2.5
pytest-cov 3.0.0
setuptools 60.1.0
sqlite3    0.0.0
Tkinter    0.0.0
toml       0.10.2
tomli      2.0.0
```

To run the tests navigate to the tests directory and enter the following command,

```bash
pytest -lv --cov src  unit/
```

The result will be similar to this, 

```bash
❯ pytest -lv --cov src  unit/
================================================== test session starts ===================================================
platform freebsd13 -- Python 3.8.12, pytest-6.2.5, py-1.11.0, pluggy-1.0.0 -- /usr/home/<your project>/venv38/bin/python3.8
cachedir: .pytest_cache
rootdir: /usr/home/rgeorgia/PycharmProjects/networkmgr-fork
plugins: cov-3.0.0
collected 7 items                                                                                                        

unit/test_net_api.py::test_default_card_returns_str PASSED                                                         [ 14%]
unit/test_net_api.py::test_card_online PASSED                                                                      [ 28%]
unit/test_net_api.py::test_card_not_online PASSED                                                                  [ 42%]
unit/test_net_api.py::test_connection_status_card_is_none PASSED                                                   [ 57%]
unit/test_net_api.py::test_connection_status_card_is_default PASSED                                                [ 71%]
unit/test_net_api.py::test_connection_status_card_is_wlan_not_connected PASSED                                     [ 85%]
unit/test_net_api.py::test_connection_status_card_is_wlan_connected PASSED                                         [100%]

-------- coverage: platform freebsd13, python 3.8.12-final-0 ---------
Name                                                                Stmts   Miss  Cover
---------------------------------------------------------------------------------------
/usr/home/rgeorgia/PycharmProjects/networkmgr-fork/src/net_api.py     199    119    40%
---------------------------------------------------------------------------------------
TOTAL                                                                 199    119    40%


=================================================== 7 passed in 0.11s ====================================================


```
