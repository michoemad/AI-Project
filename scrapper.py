import twint
import pandas as pd

reps = pd.read_csv('./rep_names.csv')
# reps = reps.iloc[524:]git

counter = {'Democratic Party': 0,
		   'Republican Party': 0}
for index, row in reps.iterrows():
	try:
		user_name = row['Twitter_username']
		party = row['Political_party']
		config = twint.Config()
		config.Lang = 'en'
		config.Pandas = True # output to pandas format
		config.Username = user_name
		config.Hide_output = True # avoid terminal spam
		config.Since = '2020-1-20' # scrape 1 year at a time
		# config.Limit = 2
		config.Until = '2021-1-20'
		#running search
		twint.run.Search(config)
	except Exception as e:
		print(e)
		continue
	if not len(twint.output.panda.Tweets_df):
		print('No tweets from: ', user_name)
		continue
	tmp = twint.output.panda.Tweets_df[['tweet','id','conversation_id']]
	tmp['party'] = party[0]
	tmp.to_csv (r'./2020_detailed_tweets.csv', mode='a', index=False, header=True)
	counter[party] += len(tmp)
	print(counter)
print('=' * 25)
print('Done Scrapping! Scrapped: ', counter)
print('=' * 25)