# WiFi-SilentDisco

Silent Disco Solution Via Wifi - Local network. Enabling everyone to start a headphone party Silent Disco. may it be at home or Outside.







Objective:

Start with a minimal, reliable pipeline on a local LAN: OBS → OvenMediaEngine (OME) via RTMP → VLC via HLS/LL-HLS. This proves base functionality (one machine publishes; another on Wi-Fi plays). Ultra-low-latency WebRTC and sync features come later.


## Local Test
- Start the stack: `docker compose up -d`
- In OBS: set **Server** to `rtmp://<HOST_IP>:1935/app` and **Stream Key** to `stream`
- In VLC (another device on the same Wi-Fi): use *Open Network Stream* with either `http://<HOST_IP>:3333/app/stream/llhls.m3u8` or `http://<HOST_IP>:3333/app/stream/master.m3u8?format=ts`
- Note: If LL-HLS fails in VLC, try the HLS-TS URL.
