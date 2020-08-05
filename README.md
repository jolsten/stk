# Quick Start

## Run an instance of STK and connect to it via socket
```python
import stk

s = stk.Run(host='localhost', port=5001)
s.run()
s.connect()

s.send('Unload / *')
s.send('New / Scenario New_Scenario_Name')
```

## Connect to an already-running instance of STK
```python
import stk

s = stk.Connect(host='localhost', port=5001)
s.connect()

s.send('Unload / *')
s.send('New / Scenario New_Scenario_Name')
```
