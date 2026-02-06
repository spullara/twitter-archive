#!/bin/bash
# ==============================================================================
# TWEET CATEGORY MERGE SCRIPT
# ==============================================================================
#
# PURPOSE: Reduce category fragmentation by merging semantically similar categories.
# Uses the simple merge_categories.py tool that takes [source] [target] arguments.
#
# HOW TO USE:
#   1. Review each merge section below
#   2. Comment out (add #) any merges you don't want
#   3. Run: ./merge_categories.sh
#
# NOTE: Each call to merge_categories.py requires confirmation (y/n).
# To run non-interactively: yes | ./merge_categories.sh
#
# BACKUP FIRST (recommended):
#   cp twitter.db twitter.db.backup
#
# ==============================================================================

set -e  # Exit on any error

# Change to script directory
cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "============================================================"
echo "CATEGORY MERGE SCRIPT"
echo "Using: python merge_categories.py [source] [target]"
echo "============================================================"
echo ""

# ==============================================================================
# GROUP 1: Tech Discussion/Commentary/Observation → tech-discussion
# ==============================================================================
# RATIONALE: All forms of tech-related commentary. The distinction between
# "discussion", "commentary", "observation", and "opinion" is too granular.
# They all represent sharing thoughts about tech topics.

echo "GROUP 1: Tech Discussion"

# tech-commentary → tech-discussion
# Sample: "@shivon Written by GPT-1."
python merge_categories.py tech-commentary tech-discussion

# tech-observation → tech-discussion
# Sample: "took my @maticrobots to the office yesterday and overnight it mapped out..."
python merge_categories.py tech-observation tech-discussion

# tech-opinion → tech-discussion
# Sample: "@bgoldy not all frameworks are vulnerable. some are completely disallowing..."
python merge_categories.py tech-opinion tech-discussion

echo ""

# ==============================================================================
# GROUP 2: Tech Interaction/Social → tech-interaction
# ==============================================================================
# RATIONALE: All social interactions in tech/internet contexts. The distinction
# between where the interaction happens (Twitter vs internet) is not meaningful.

echo "GROUP 2: Tech Interaction"

# tech-twitter-interaction → tech-interaction
# Sample: "@kevinmarks @heathr shouldn't it be 4s?"
python merge_categories.py tech-twitter-interaction tech-interaction

# internet-interaction → tech-interaction
# Sample: "the whole twitter noise thing is based on an irrelevant statistic..."
python merge_categories.py internet-interaction tech-interaction

# tech-internet-interaction → tech-interaction
# Sample: "@mdkail @seldo actually though, IRC never really federated..."
python merge_categories.py tech-internet-interaction tech-interaction

echo ""

# ==============================================================================
# GROUP 3: Link Sharing → link-share
# ==============================================================================
# RATIONALE: The core action is sharing a link. Whether it's tech or news
# doesn't change the fundamental purpose.

echo "GROUP 3: Link Sharing"

# tech-link-share → link-share
# Sample: "RT @lpolovets: Nice job, @sampullara! http://t.co/W7U39Yj1S6"
python merge_categories.py tech-link-share link-share

# news-sharing → link-share
# Sample: "press has confirmed that announcement containing photo of a car was referring to a car"
python merge_categories.py news-sharing link-share

echo ""

# ==============================================================================
# GROUP 4: Tech Industry → tech-industry
# ==============================================================================
# RATIONALE: All content about the tech industry itself (companies, trends,
# business news). The distinction between commentary/news/observation/speculation
# is about tone, not subject matter.

echo "GROUP 4: Tech Industry"

# tech-industry-commentary → tech-industry
# Sample: "@SparksZilla @DanielleMorrill engineers whatever they want. others not so much."
python merge_categories.py tech-industry-commentary tech-industry

# tech-industry-news → tech-industry
# Sample: "This is starting to happen at small scale, you know just all of Apple's AI features"
python merge_categories.py tech-industry-news tech-industry

# tech-industry-observation → tech-industry
# Sample: "@rsarver i enjoyed it but don't know how anyone outside the industry could understand"
python merge_categories.py tech-industry-observation tech-industry

# tech-industry-speculation → tech-industry
# Sample: "@ThomasAlxDmy @bawejakunal Might to enlist the Boring company to make this habitable."
python merge_categories.py tech-industry-speculation tech-industry

# tech-industry-nostalgia → tech-industry
# Sample: "@gsaab @scottmcnealy mine was better. can't even copy me properly."
python merge_categories.py tech-industry-nostalgia tech-industry

echo ""

# ==============================================================================
# GROUP 5: Brief Interactions → brief-interaction
# ==============================================================================
# RATIONALE: All short, simple interactions. The many sub-categories fragment
# what is essentially the same type of content: brief social engagement.

echo "GROUP 5: Brief Interactions"

# brief-social-comment → brief-interaction
# Sample: "@joshuabaer looks cool but a clicky keyboard would not go over well at our office..."
python merge_categories.py brief-social-comment brief-interaction

# brief-social-commentary → brief-interaction
# Sample: "@mccrory the bare feet on the airplane"
python merge_categories.py brief-social-commentary brief-interaction

# brief-amusement → brief-interaction
# Sample: "@pandemona not the best solution in the world but the fake niceness was enough..."
python merge_categories.py brief-amusement brief-interaction

# brief-observation → brief-interaction
# Sample: "@dannysullivan @cnn that quake was so last hour."
python merge_categories.py brief-observation brief-interaction

# brief-personal-statement → brief-interaction
# Sample: "@marcprecipice school starts for us tomorrow :("
python merge_categories.py brief-personal-statement brief-interaction

# brief-professional-comment → brief-interaction
# Sample: "@abrams @shervin @nxrfelix @alexwilliams did a professional investor join their board?"
python merge_categories.py brief-professional-comment brief-interaction

# brief-industry-comment → brief-interaction
# Sample: "@jwatte i mean circular but bgp is certainly shared"
python merge_categories.py brief-industry-comment brief-interaction

# brief-commentary-share → brief-interaction
# Sample: "@HiveTheory longer form text"
python merge_categories.py brief-commentary-share brief-interaction

# brief-professional-praise → brief-interaction
# Sample: "@chirags the engineering team over here at @bagchk doesn't screw around..."
python merge_categories.py brief-professional-praise brief-interaction

# brief-insult → brief-interaction
# Sample: "@kevinmitnick hopefully we will never see your nude selfies on 4chan."
python merge_categories.py brief-insult brief-interaction

echo ""

# ==============================================================================
# GROUP 6: Personal Content → personal
# ==============================================================================
# RATIONALE: All personal (non-tech) content about life, thoughts, feelings.
# Consolidate into the standard "personal" category for cleaner analysis.

echo "GROUP 6: Personal Content"

# personal-observation → personal
# Sample: "Talked to a 13-yr old. He loves Yahoo, MySpace and YouTube..."
python merge_categories.py personal-observation personal

# personal-opinion → personal
# Sample: "@pmarca @abrams @mattocko @peteskomoroch that entire article reads like fantasy..."
python merge_categories.py personal-opinion personal

# personal-reflection → personal
# Sample: "@om thanks for the chat this afternoon! you've got me thinking slower..."
python merge_categories.py personal-reflection personal

# personal-complaint → personal
# Sample: "@dnak @fffabulous @travisk @Uber not a great experience for a $60+ ride"
python merge_categories.py personal-complaint personal

echo ""

# ==============================================================================
# GROUP 7: Tech Questions/Requests → tech-question
# ==============================================================================
# RATIONALE: All represent asking for something (help, info, recommendations)
# related to tech. The distinction between "question", "request", and "help"
# is semantic rather than functional.

echo "GROUP 7: Tech Questions"

# tech-request → tech-question
# Sample: "sadly my @WavefrontHQ account was finally shut down... what's the best observability..."
python merge_categories.py tech-request tech-question

# tech-help → tech-question
# Sample: "@mccv do you guys need gc help? i can come by :)"
python merge_categories.py tech-help tech-question

echo ""

# ==============================================================================
# GROUP 8: Tech Recommendations/Suggestions → tech-recommendation
# ==============================================================================
# RATIONALE: All represent recommending or suggesting something (tools, practices).
# The opposite of Group 7 - providing guidance rather than seeking it.

echo "GROUP 8: Tech Recommendations"

# tech-suggestion → tech-recommendation
# Sample: "@kevinmarks it isn't a post, it is 'go to notification settings and turn on...'"
python merge_categories.py tech-suggestion tech-recommendation

# tech-advice → tech-recommendation
# Sample: "@kevinmarks you should update your blog entry to at least tell people..."
python merge_categories.py tech-advice tech-recommendation

# tech-tip → tech-recommendation
# Sample: "tap and hold when composing an email message to bring up your drafts..."
python merge_categories.py tech-tip tech-recommendation

# recommendation → tech-recommendation
# Sample: "@nateliason if you have two you are probably fine. you may need a bigger car..."
python merge_categories.py recommendation tech-recommendation

echo ""

# ==============================================================================
# GROUP 9: Tech Problems/Issues → tech-problem
# ==============================================================================
# RATIONALE: All represent frustration with technology - bugs, service outages,
# product issues, complaints. Consolidated for sentiment analysis.

echo "GROUP 9: Tech Problems"

# tech-bug → tech-problem
# Sample: "@fffabulous @travisk just took @Uber to SF and then reopened the app..."
python merge_categories.py tech-bug tech-problem

# tech-service-issue → tech-problem
# Sample: "it amazes me that GCP still has global outages this late in the cloud game"
python merge_categories.py tech-service-issue tech-problem

# tech-app-issue → tech-problem
# Sample: "@semil i have 100+ friends on it, their post frequency dropped like a stone..."
python merge_categories.py tech-app-issue tech-problem

# tech-complaint → tech-problem
# Sample: "@octal @VerizonWireless never use Verizon...."
python merge_categories.py tech-complaint tech-problem

# tech-consumer-complaint → tech-problem
# Sample: "@dweekly @onelawn we looked at reviews online..."
python merge_categories.py tech-consumer-complaint tech-problem

# consumer-complaint → tech-problem
# Sample: "@octal @VerizonWireless oops, i meant to say I never *used* verizon."
python merge_categories.py consumer-complaint tech-problem

# tech-disappointment → tech-problem
# Sample: "it amazes me that GCP still has global outages this late in the cloud game"
python merge_categories.py tech-disappointment tech-problem

# tech-troubleshooting → tech-problem
# Sample: "@dhh do you forward from other accounts? That happens to me..."
python merge_categories.py tech-troubleshooting tech-problem

echo ""

# ==============================================================================
# SUMMARY
# ==============================================================================

echo "============================================================"
echo "MERGE COMPLETE"
echo "============================================================"
echo ""
echo "9 groups processed with ~45 category merges"
echo ""
echo "To see current stats: python -c \"import duckdb; c=duckdb.connect('twitter.db'); print(c.execute('SELECT category, COUNT(*) as cnt FROM tweet_categories GROUP BY category ORDER BY cnt DESC LIMIT 20').fetchall())\""

