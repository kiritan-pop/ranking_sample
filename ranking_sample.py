# -*- coding: utf-8 -*-

# Mastodon.py モジュールを認証なしで使えるように改造したやつ
from mastodon_kai import Mastodon, StreamListener

from pprint import pprint as pp
import re
import json
import unicodedata
import requests
import threading, queue
from time import sleep
from pytz import timezone
from datetime import datetime, timedelta
import warnings, traceback
from bs4 import BeautifulSoup
from collections import defaultdict

DELAYTIME = 60
url_ins = open("instance.txt").read()

mastodon = Mastodon(
    access_token='user.secret',
    api_base_url=url_ins)

# 認証なしタイムライン取得用
publicdon = Mastodon(api_base_url=url_ins)

PostQ = queue.Queue()

#######################################################
# エラー時のログ書き込み
def error_log():
    jst_now = datetime.now(timezone('Asia/Tokyo'))
    ymdhms = jst_now.strftime("%Y/%m/%d %H:%M:%S")
    with open('error.log', 'a') as f:
        f.write('\n####%s####\n'%ymdhms)
        traceback.print_exc(file=f)
    print("###%s 例外情報\n"%ymdhms + traceback.format_exc())


#######################################################
# スケジューラー！
def scheduler(func, hhmm_list, *args):
    #func:起動する処理
    #hhmm_list:起動時刻
    while True:
        sleep(10)
        try:
            #時刻指定時の処理
            jst_now = datetime.now(timezone('Asia/Tokyo'))
            hh_now = jst_now.strftime("%H")
            mm_now = jst_now.strftime("%M")
            for hhmm in hhmm_list:
                if len(hhmm.split(":")) == 2:
                    hh,mm = hhmm.split(":")
                    if (hh == hh_now or hh == '**') and mm == mm_now:
                        func(args)
                        sleep(60)
        except Exception:
            error_log()


#######################################################
# トゥート処理
def toot(toot_now, g_vis='direct', rep=None, spo=None, media_ids=None, interval=0):
    def qput(toot_now, g_vis, rep, spo, media_ids):
        PostQ.put((exe_toot,(toot_now, g_vis, rep, spo, media_ids)))

    th = threading.Timer(interval=interval,function=qput,args=(toot_now, g_vis, rep, spo, media_ids))
    th.start()

def exe_toot(toot_now, g_vis='direct', rep=None, spo=None, media_ids=None, interval=0):
    if spo:
        spo_len = len(spo)
    else:
        spo_len = 0
    if rep != None:
        try:
            mastodon.status_post(status=toot_now[0:490-spo_len], visibility=g_vis, in_reply_to_id=rep, spoiler_text=spo, media_ids=media_ids)
        except Exception:
            sleep(2)
            mastodon.status_post(status=toot_now[0:490-spo_len], visibility=g_vis, in_reply_to_id=None, spoiler_text=spo, media_ids=media_ids)
    else:
        mastodon.status_post(status=toot_now[0:490-spo_len], visibility=g_vis, in_reply_to_id=None, spoiler_text=spo, media_ids=media_ids)

    jst_now = datetime.now(timezone('Asia/Tokyo'))
    ymdhms = jst_now.strftime("%Y%m%d %H%M%S")
    print("%s🆕toot:"%ymdhms + toot_now[0:300] + ":" + g_vis )

#######################################################
# ファボ処理
def fav_now(id):  # ニコります
    PostQ.put((exe_fav_now,(id,)))

def exe_fav_now(id):  # ニコります
    try:
        status = mastodon.status(id)
    except Exception as e:
        print(e)
    else:
        if status['favourited'] == False:
            #mastodon.status_favourite(id)
            th = threading.Timer(interval=2,function=mastodon.status_favourite,args=(id,))
            th.start()
            jst_now = datetime.now(timezone('Asia/Tokyo'))
            ymdhms = jst_now.strftime("%Y%m%d %H%M%S")
            print("%s🙆Fav"%ymdhms)

#######################################################
# アンケ回答（サンプル）
def enquete_vote(id,idx):
    PostQ.put((exe_enquete_vote,(id,idx)))

def exe_enquete_vote(id,idx):
    th = threading.Timer(interval=2,function=mastodon.vote,args=(id, idx))
    th.start()

#######################################################
# ブースト
def boost_now(id):  # ぶーすと！
    PostQ.put((exe_boost_now, (id,)))

def exe_boost_now(id):  # ぶーすと！
    try:
        status = mastodon.status(id)
    except Exception as e:
        print(e)
    else:
        if status['reblogged'] == False:
            mastodon.status_reblog(id)
        else:
            mastodon.status_unreblog(id)
            sleep(2)
            mastodon.status_reblog(id)
        print("🙆boost")

#######################################################
# ブーキャン
def boocan_now(id):  # ぶーすと！
    PostQ.put((exe_boocan_now, (id,)))

def exe_boocan_now(id):  # ぶーすと！
    status = mastodon.status(id)
    if status['reblogged'] == True:
        mastodon.status_unreblog(id)
        print("🙆unboost")

#######################################################
# フォロー
def follow(id):
    PostQ.put((exe_follow,(id,)))

def exe_follow(id):
    mastodon.account_follow(id)
    # th = threading.Timer(interval=8,function=mastodon.account_follow,args=(id,))
    # th.start()
    print("♥follow")

#######################################################
# トゥー消し
def toot_delete(id,interval=5):
    def qput(id):
        PostQ.put((exe_toot_delete,(id,)))

    th = threading.Timer(interval=interval,function=qput,args=(id,))
    th.start()

def exe_toot_delete(id):
    mastodon.status_delete(id)
    print("♥toot delete")


#######################################################
# post用worker
def th_post():
    while True:
        try:
            func,args = PostQ.get()
            func(*args)
            sleep(2.0)
            # sleep(2.0+CM.get_coolingtime())
        except Exception as e:
            print(e)
            error_log()


#######################################################
# トゥート内容の標準化・クレンジング
def content_cleanser(content):
    tmp = BeautifulSoup(content.replace("<br />", "___R___").strip(), 'lxml')
    hashtag = ""
    for x in tmp.find_all("a", rel="tag"):
        hashtag = x.span.text
    for x in tmp.find_all("a"):
        x.extract()

    if tmp.text == None:
        return ""

    rtext = ''
    ps = []
    for p in tmp.find_all("p"):
        ps.append(p.text)
    rtext += '。\n'.join(ps)
    rtext = unicodedata.normalize("NFKC", rtext)
    rtext = re.sub(r'([^:])@', r'\1', rtext)
    rtext = rtext.replace("#", "")
    rtext = re.sub(r'(___R___)\1{2,}', r'\1', rtext)
    rtext = re.sub(r'___R___', r'\n', rtext)
    if hashtag != "":
        return rtext + " #" + hashtag
    else:
        return rtext


#######################################################
# ランキング処理
def ranking(delay=10):
    hh_now = ranking_sub1(delay=delay)
    ranking_sub2(hh_now)

def ranking_sub1(delay=10):
    jst_now = datetime.now(timezone('Asia/Tokyo'))
    sleep(delay*60)    # ニコる数反映まで、おそよn分タイムラグあるので待つ

    # 0時起動の場合は１日分、それ以外は１時間分のトゥートを取得
    hh_now = jst_now.strftime("%H")
    if hh_now == '00':
        diff = timedelta(hours=24)
    else:
        diff = timedelta(hours=1)

    # トゥート取得処理
    statuses_json = {}
    last_id = None
    break_sw = False
    cnt = 0
    while True:
        sleep(2)
        statuses = publicdon.timeline_local(max_id=last_id, limit=40)
        cnt += len(statuses)
        for status in statuses:
            if jst_now > status['created_at'] + diff:
                break_sw = True
                break
            last_id = status['id']
            created_at = status['created_at'].astimezone(timezone('Asia/Tokyo')).strftime("%Y/%m/%d %H:%M:%S%z")
            text = content_cleanser(status['content'])
            media_urls = []
            for media in status['media_attachments']:
                media_urls.append(media['url'])

            statuses_json[status["id"]] = [created_at, text, status['favourites_count'],
                                        status['reblogs_count'], status['account']['acct'], media_urls]

        print(f'{created_at} {cnt}件')

        if break_sw == True:
            break

    f = open("statuses.json","w")
    json.dump(statuses_json, f, ensure_ascii=False, indent=4)

    return hh_now


def ranking_sub2(hh_now):
    users_cnt = defaultdict(int)
    users_size = defaultdict(int)
    fav_cnt = defaultdict(int)
    boost_cnt = defaultdict(int)
    faboo_cnt = defaultdict(int)
    fav_acct_cnt = defaultdict(int)
    faboo_rate = defaultdict(float)
    faboo_cnt_list = defaultdict(list)
    footer = "\n#きりランキング #きりぼっと @kiritan"
    if hh_now == "00":
        asikiri = 30
    else:
        asikiri = 5

    f = open("statuses.json", "r")
    statuses_json = json.load(f)

    for id, (created_at, text, f_c, r_c, acct, media_urls) in statuses_json.items():
        fav_cnt[id] = f_c
        boost_cnt[id] = r_c

        users_size[acct] += len(text)
        users_cnt[acct] += 1
        fav_acct_cnt[acct] += f_c
        faboo_cnt[acct] += f_c + r_c
        faboo_cnt_list[acct].append(f_c + r_c)

        if users_cnt[acct] >= asikiri:
            faboo_rate[acct] = faboo_cnt[acct] * 100.0 / users_cnt[acct]

    if hh_now == "00":
        spoiler_text = "１日のトゥート数ランキング"
    else:
        spoiler_text = "毎時トゥート数ランキング"
    body = ""
    total_cnt = 0
    total_faboo_cnt = 0
    for i, (acct, cnt) in enumerate(sorted(users_cnt.items(), key=lambda x: -x[1])):
        total_cnt += cnt
        total_faboo_cnt += faboo_cnt[acct]
        if len(body) < 420:
            if i == 0:
                body += "🥇 " 
            if i == 1:
                body += "🥈 "
            if i == 2:
                body += "🥉 "
            if i == 3:
                body += "🏅 "
            if i == 4:
                body += "🏅 "
            body += f":@{acct}:{cnt:3}  "
            if i % 3 == 1 or i <= 4:
                body += "\n"

    body = f"📝全体 {total_cnt} toots\n{body}"
    body += footer
    toot(body, g_vis='public', spo=spoiler_text)

    #ニコられランキング
    sleep(DELAYTIME)
    if hh_now == "00":
        spoiler_text = "１日のニコられ数ランキング"
    else:
        spoiler_text = "毎時ニコられ数ランキング"
    body = ""
    total_fav_cnt = 0
    for i, (acct, cnt) in enumerate(sorted(fav_acct_cnt.items(), key=lambda x: -x[1])):
        total_fav_cnt += cnt
        if len(body) < 420:
            if i == 0:
                body += "🥇 "
            if i == 1:
                body += "🥈 "
            if i == 2:
                body += "🥉 "
            if i == 3:
                body += "🏅 "
            if i == 4:
                body += "🏅 "
            body += f":@{acct}:{cnt:3}  "
            if i % 3 == 1 or i <= 4:
                body += "\n"

    body = f"📝全体 {total_fav_cnt} ニコる\n{body}"
    body += footer
    toot(body, g_vis='public', spo=spoiler_text)

    sleep(DELAYTIME)
    if hh_now == "00":
        spoiler_text = "１日のニコブ率ランキング"
    else:
        spoiler_text = "毎時ニコブ率ランキング"
    body = ""
    for i, (acct, rate) in enumerate(sorted(faboo_rate.items(), key=lambda x: -x[1])):
        if len(body) < 380:
            if i == 0:
                body += "🥇 "
            if i == 1:
                body += "🥈 "
            if i == 2:
                body += "🥉 "
            if i == 3:
                body += "🏅 "
            if i == 4:
                body += "🏅 "
            body += f":@{acct}:{rate:.1f}  "
            if i % 2 == 1 or i <= 4:
                body += "\n"

    body += "\n※ニコブ率：（ニコられ数＋ブーストされ数）÷トゥート数\n"
    body += f"※{asikiri}トゥート未満の人は除外"
    body += footer
    toot(body, g_vis='public', spo=spoiler_text)

    sleep(DELAYTIME)
    if hh_now == "00":
        spoiler_text = "昨日最もニコられたトゥートは……"
    else:
        spoiler_text = "ここ１時間で最もニコられたトゥートは……"
    for id, cnt in sorted(fav_cnt.items(), key=lambda x: -x[1])[:1]:
        boost_now(id)
        sleep(5)
        text = statuses_json[id][1]
        f_c = statuses_json[id][2]
        r_c = statuses_json[id][3]
        acct = statuses_json[id][4]

        body = f":@{acct}:＜「{text} 」\n#{f_c:2}ニコる／{r_c:2}ブースト"
        body += f"\n https://friends.nico/@{acct}/{id}"
        body += footer
        toot(body, g_vis='public', spo=spoiler_text)


#######################################################
# メイン
def main():
    threads = []
    #タイムライン応答系
    threads.append( threading.Thread(target=th_post) )
    #スケジュール起動系(時刻)
    threads.append(threading.Thread(
        target=scheduler, args=(ranking, ['**:00'])))

    for th in threads:
        th.start()

if __name__ == '__main__':
    main()
