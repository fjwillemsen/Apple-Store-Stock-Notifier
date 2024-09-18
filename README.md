# Apple Store Stock Notifier

<!-- ### Apple Store Stock Notifier monitors the availability of selected Apple devices in selected Apple stores, and sends you a notification when devices are available! -->

**This software will immediately send you a notification via Telegram when one of your coveted Apple Devices is available in the selected Apple Stores!**
In addition, it offers various tools (such as graphs) to analyze the availability of the selected devices from the comfort of your smartphone / tablet / teapot / desktop etc. (whatever Telegram runs on). 
It is intended to run on an always-on device (such as a Raspberry Pi), and requires an internet connection and a Telegram account. 

This software is built on a modified version of [Apple-Store-Reserve-Monitor](https://github.com/insanoid/Apple-Store-Reserve-Monitor) by [insanoid](https://github.com/insanoid). 

## Installation (App)
The app can be downloaded from the [releases page](). 

## Installation (CLI)
How to install the command-line interface monitor:
1. Clone this repository and `cd` to it. 
2. Execute `pip install -r requirements.txt`.
3. Adapt the `config.json` file to your needs (see under "use"). 
4. Create a Telegram bot at @botfather in telegram app to inform you and enter the required details in `parameters.py`.
5. [Create a Telegram API](https://my.telegram.org/apps) to send a message to the bot and enter the required details (api_id, api_hash) in `parameters.py`.
6. Run the monitor with `python monitor.py`. 
7. (optional) Send `/setcommands` to the Telegram Botfather chat, select the bot and send the output under "Commands available:" to make the commands easily accessible from the chat. 
8. (optional) to build the GUI app, run `nicegui-pack --windowed --name "Apple Stock Notifier" main.py`. 

Running the pip numpy on the Raspberry Pi can be cumbersome. 
If you get errors pertaining to "Importing the numpy C-extensions failed", try running `sudo apt-get install python-dev libatlas-base-dev`. 

## Use
It's as simple as entering the device and Apple Store you want in `config.json` and running `python module.py`. 
The model in `config.json` is the model part number, that can be looked up [here](https://www.techwalls.com/iphone-13-pro-model-number-a2483-a2636-a2638-a2639-a2640-differences/). 
The store in `config.json` is the store ID, a list of which can be looked up [here](https://gist.github.com/iF2007/ff127f7722af91c47c0cb44d6c1e961d), defaults to all stores in the zip-code region. To only use specific stores, leave the zip-code empty. If selecting multiple stores without a zip-code region, a separate request will be made for each store. 
`config.json` is part of the interface of Apple Store Reserve Monitor, more information on how to use this [here](https://github.com/insanoid/Apple-Store-Reserve-Monitor).

You can change the parameters regarding intervals, paths, use of proxies etc. from the defaults in `parameters.py`. 

It is recommended to run this on a computer that is always on and always has an active internet connection (think of the environment when doing this!). 
Raspberry Pi and similar computing boards are often good choices. 
You may want to set up a job to start this automatically using crontab or bashrc if you are running this on a Raspberry Pi, so it can run autonomously. 

**Please use this software responsibly!** 
Do not set a low polling interval, both for your own benefit (you will be blocked) as for the other users of Apple's service. 
In general, the defaults set are fine for being notified in time. 
The intended use is for people to be able to get an Apple device that is often out of stock for their own use. 
Do not use this software for scalping, price gouging or any other use that is unethical. 

## Proxies
Randomized proxies help you make requests for a prolonged period of time without your IP-address being blocked by Apple's server.
For this [http-request-randomizer](https://github.com/pgaref/HTTP_Request_Randomizer#http-request-randomizer-----) by [pgaref](https://github.com/pgaref/HTTP_Request_Randomizer/commits?author=pgaref) (licensed under MIT license) is used. 
If randomized proxies are enabled in `parameters.py`, a list of free proxies will be generated. 
When a request is made, a random proxy is selected from this list. 
If the proxy does not return a response within the timeout window, the proxy is removed from the list. 
Because free proxies are often slow and unreliable, for each request, it will fallback to a non-proxied request after attempting a proxy unsuccesfully. 
However, because unresponsive proxies are removed from the list, in most cases this random proxy system becomes reliable after a while. 
Keep in mind that free proxies only remain active for a very short time (days or even hours), so if this program is ran for a long time, the list will become empty, at which point it reloads the proxy list. 
Using the randomized proxies is significantly slower than direct requests, but prevent your IP address from being blocked. 

## Licensing
This software builts on other open source software. 
As such, it is [MIT licensed](). 