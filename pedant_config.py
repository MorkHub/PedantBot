CONF = {
    'log_format'   : '[%(asctime)s] [%(name)s] [%(levelname)s] [%(module)s:%(lineno)s %(funcName)s] %(message)s',
    
    'admins'       : ['154542529591771136', #TheMork#1944
		    	      '154543065594462208'  #Shwam3#8508
		    	     ],

	'dir_pref'     : '/home/mark/Documents/pedant/',
	'cmd_pref'     : '$',
	'logfile'      : 'pedant.log',
	'date_format'  : '%A %d %B %Y @ %I:%M%p',
	'VERSION'      : '2.0.5',
	'oauth_token'  : 'MTY5MTEyMzU5OTM4MjkzNzYw.C1FhGw.77rBAVDk3zCAIpF8jB0p4wDxJXQ',
}

MESG = {
    'error'    : '**Error running command**: {0.args[0]}',
    'nopermit' : '{0.author.mention} is not in the list of sudoers. This incident will be reported.',
    'shutdown' : 'Shutting down... :wave:',

    'cmd_help'     : '**Help for {0.command_name}**\n```{0.__doc__}\nUSAGE: {0.usage}```',
    'cmd_doc'      : ' - {0.usage}: {0.__doc__}',
    'cmd_usage'    : '**Error:** Invalid usage.\n```USAGE: {0.usage}```',
    'cmd_notfound' : 'Command `{0}` not found.',
    'cmd_list'     : '**Commands:**```-------- Standard --------\n{0}-------- Admin --------\n{1}```',

    'st_start' : ':race_car: **Speedtest Results**\nWorking... :hourglass_flowing_sand:',
    'st_ping'  : ':race_car: **Speedtest Results**\n**Ping:** {}ms\nWorking... :hourglass_flowing_sand:',
    'st_up'    : ':race_car: **Speedtest Results**\n**Ping:** {}ms\n**Download Speed:** {}Mb/s\nWorking... :hourglass_flowing_sand:',
    'st_down'  : ':race_car: **Speedtest Results**\n**Ping:** {}ms\n**Download Speed:** {}Mb/s\n**Upload Speed:** {}Mb/s',
    'st_error' : '\n**An error has occured**',

    'define_none'  : 'No results found for: `{0}`',
    'define_error' : '**Error:** Unable to retrieve results at this time.',
    'define_title' : 'Definition for {0}',

    'vote_title' : '**{0}**\nReact with one of the following to vote: {1}',
    'vote_timer' : '\nTime Remaining: {0}',
    'vote_ended' : '\n***Voting ended.***',
    'vote_none'  : 'Nobody submitted any valid votes :(',
    'vote_win'   : '**{0}**\nThe winning vote was: {1}\n```{graph}```',
    'digits'     : [':zero:',':one:',':two:',':three:',':four:',':five:',':six:',':seven:',':eight:',':nine:'],

    'ping'    : ':ping_pong: Pong!',
    'ip_addr' : 'IP: `{0}`',

    'calc_illegal' : '**Error:** \'{0}\' contains illegal characters.',
    'maths_illegal' : '**Error:** \'{0}\' contains illegal calculation.',

    'emoji_unsupported' : 'Only custom emoji for \'{0}\' are supported',

    'reminder_cancel'  : 'Reminder for {0} ({1[message]}) cancelled.',
    'reminder_illegal' : 'Cant set a reminder against our current laws of physics',

    'abuse_error'  : '**Error:** Either I am not in that server, or the server/channel does not exist.'
}