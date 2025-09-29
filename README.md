# WiFi-SilentDisco

Silent Disco Solution Via Wifi - Local network. Enabling everyone to start a headphone party Silent Disco. may it be at home or Outside.
we use OvenMediaEngine to make the server.
We have scripts, that even somebody without scripting knowledge can execute, the scripts will give feedback and instructions how to be used.
We will have a Guest website with the stream Player 
after it has been setup with the setup script, The Stream server can be started with a start script. this one launches a Gui where all important parameters are made visible. The server starts automatically, The gui Has Buttons to start and stop the server. It also gives Live Feedback if the server is running, and if media is being streamed. Also the amount of Guest clients is displayed.
Also in the GUI there are the instructions on how to setup OBS so it looks for what Streaming URL the user has to set obs and also the Key.








Objective:

Build a Setup script, that installs all necessary dependencies and libaries.
make the Server Start script with the Gui. Make sure everything is functional and when launched it really creates a server in the network, that OBS can stream to.
Make sure, that every necessary paths and ports are automatically set. Also dont have them hardcoded if not needed. instead, give the user a Gui option to analize for possible errors because of blcoked ports firewall or similar and then automatically change to new parameters. the stream URL and Key wil be automatically updated in this case.
Every Gui function gives user feedback.
