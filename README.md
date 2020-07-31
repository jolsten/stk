STKConnect()
    Connect to an (already running) instance of Systems ToolKit via socket
    
    Attributes
    ----------
    host : str (default:localhost)
        the hostname of the instance of STK (default: localhost)
    
    port : int
        the port number for the STK socket (default: 5001)
    
    Methods
    -------
    connect()
        attempts to connect to STK via a socket
    
    send(message)
        sends the specified message to STK 
    
    close()
        closes the socket, if it is open
    
    Examples
    --------
    s = STKConnect()
    s.connect()
    s.send('Unload / *')
    s.send(f'New / Scenario Scenario_Name')
    s.close()

STKLaunch()
    Launch an instance of AGI's Systems ToolKit (STK) and connect via socket
    
    Attributes
    ----------
    host : str (default: localhost)
        the hostname of the instance of STK (default: localhost)
    
    port : int (default: 5001)
        the port number for the STK socket (default: 5001)
    
    stk_install_dir : path-like object
        the path to the relevant STK executable
        
        Defaults: 
            Windows: C:\\Program Files\\AGI\\STK 11
            Linux  : ~/stk
    
    vendorid : str
        STK license Vendor ID; apparently necessary in a Linux environment
    
    max_attempts : int (default: 15 attempts)
        maximum number of times to attempt connecting to STK
        generally, this is a way to wait for STK to complete launching before
        the port is made available for connections
    
    poll_period : int (default: 2 seconds)
        time to wait between attempting to connect to the socket
    
    
    Methods
    -------
    launch()
        launch an instance of the STK application
    
    send(message)
        sends the specified message to STK 
    
    close_socket()
        closes the socket, if it is open
    
    close()
        shut down the STK application