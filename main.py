from os import getenv, makedirs
import logging
import shelve
from subprocess import Popen
from random import choice
from time import sleep
from datetime import datetime, timedelta
from telegram.ext import Updater, MessageHandler, CommandHandler, Filters

DEBUG = getenv('DEBUG')
admin = 13301988
ALERT_DATE = datetime(year=2018, month=12, day=16, hour=12, minute=30)
DRAW_DATE = datetime(year=2018, month=12, day=16, hour=20)
if DEBUG:
    ALERT_DATE = datetime.now() + timedelta(seconds=5)
    DRAW_DATE = datetime.now() + timedelta(seconds=15)

# init persistent database
try:
    makedirs('storage')
    makedirs('storage/images')
    makedirs('storage/images/raw')
    makedirs('storage/images/video')
except FileExistsError:
    # storage folder already present
    pass
db = shelve.open("storage/db")

# Get config from env. variables
TOKEN = getenv('TOKEN')
WEBHOOK_URL = getenv('WEBHOOK_URL', None)
if WEBHOOK_URL and WEBHOOK_URL[-1] != '/':
    WEBHOOK_URL += '/'

# Init logger
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)
logger = logging.getLogger(__name__)


# Utils
def is_female(name):
    M = ['andrea', 'luca']  # nomi maschili che finiscono in "a"
    F = ['vent']  # nomi femminili che non finiscono in "a"
    norm_name = name.lower()
    if norm_name in F:
        return True
    if norm_name in M:
        return False
    return norm_name[-1] == 'a'


def send_batch(update, msg_list):
    for txt in msg_list:
        update.message.chat.send_action("typing")
        sleep(max(0.01 * len(txt), 0.5))
        update.message.reply_text(txt, parse_mode="HTML")


def is_registered(user):
    global db
    return str(user.id) in db


def get_status(user):
    global db
    user_id = str(user.id)
    return db[user_id]["status"]


def update_field(user_id, field, value):
    global db
    user = db[user_id]
    user[field] = value
    db[user_id] = user


def set_status(user, status):
    global db
    user_id = str(user.id)
    if user_id not in db:
        save_photo(user)
        db[user_id] = {
            "first_name": user.first_name,
            "wishlist": None,
            "address": None,
            "status": status,
        }
    else:
        update_field(user_id, 'status', status)


def store_list(user, link):
    global db
    user_id = str(user.id)
    if user_id not in db:
        set_status(user, None)
    update_field(user_id, 'wishlist', link)


def store_addr(user, addr):
    global db
    user_id = str(user.id)
    if user_id not in db:
        set_status(user, None)
    update_field(user_id, 'address', addr)


def save_photo(user):
    profile_pics = user.get_profile_photos()
    path = 'storage/images/raw/{}.jpg'
    if len(profile_pics.photos) > 0:
        max(profile_pics.photos[0], key=lambda p: p.width).get_file().download(
            path.format(user.id))
    else:
        # copy default pic
        pass


def make_gif(user_id):
    cmd = "ffmpeg -y -f image2 -framerate 60 \
        -i storage/images/raw/{user_id}.jpg \
        -i rain.gif -ignore_loop 0 \
        -filter_complex \"[0][1]overlay=0\" \
        ./storage/images/video/{user_id}.mp4\
    ".format(user_id=user_id)
    return Popen(['/bin/bash', '-c', cmd])


def is_valid(user_id):
    global db
    user = db[str(user_id)]
    return user['first_name'] and user['wishlist'] and user['address']


# Handlers
def alert(bot, job):
    global db

    for user_id in db:
        txt = """
IGNORARE LE ESTRAZIONI GIÀ USCITE FINO AD ORA.

Per una serie di condizioni, l'estrazione reale e definitiva verrà inviata stasera alle 19.
Ripeto: non fate i regali per il momento, se li avete già fatti <b>annullateli</b>!

Sembra anche che ci siano wishlist <b>senza oggetti spediti prima di Natale</b>, per favore ricontrollate le vostre liste e accertatevene.
        """
        bot.send_message(user_id, txt, parse_mode='HTML')

    unregistered = [u_id for u_id in db if not is_valid(u_id)]
    for user_id in unregistered:
        txt = """
Il tempo stringe e non hai ancora completato la registrazione!

Se vuoi partecipare utilizza /set_list per impostare la tua wishlist Amazon e /set_address per impostare l'indirizzo di spedizione.
        """
        bot.send_message(user_id, txt)


def draw_matches(bot, job):
    global db
    for user_id in db:
        p = make_gif(user_id)
        p.wait()

    unchosen = [u_id for u_id in db if is_valid(u_id)]
    matches = []  # [u9, u4, u2]: u9 -gift-> u4, u4 -g-> u2, u2 -g-> u9
    for _ in range(len(unchosen)):
        unchosen = [u_id for u_id in unchosen if u_id not in matches]
        matches.append(choice(unchosen))

    for i in range(len(matches)):
        user_id = matches[i]
        gift_to_id = matches[(i + 1) % len(matches)]
        gift_to = db[gift_to_id]

        if DEBUG:
            bot.send_message(
                admin, '{} -> {}'.format(db[user_id]['first_name'],
                                         gift_to['first_name']))
            user_id = str(admin)

        caption = """
Devi fare un regalo a {}!
        """.format(gift_to['first_name'])
        with open('storage/images/video/{}.mp4'.format(gift_to_id), 'rb') as f:
            bot.send_animation(user_id, f, caption=caption)
        to_send = [
            """
Il link alla sua wishlist è {}, scegli un bel regalo mi raccomando 🎁.
            """.format(gift_to['wishlist']), """
L'indirizzo a cui dovrai spedirlo invece è:
{}

assicurati che arrivi entro Natale, ovviamente!
            """.format(gift_to['address'])
        ]
        for txt in to_send:
            bot.send_message(user_id, txt)


def send_completed(update):
    if is_valid(update.message.from_user.id):
        update.message.reply_text('''
Fantastico, hai completato la registrazione. Non ti rimane che aspettare il giorno dell'estrazione, ti scrivo io :)

Nel caso dovessi aggiornare i tuoi dati, puoi riusare i miei comandi senza alcun problema.
        ''')


def start(bot, update):
    user = update.message.from_user
    name = user.first_name
    to_send = [
        '''
🎅 Ho-ho-hoo! <b>Hai fatto {} {}?</b>

Son figo,
son bello,
son il tu' babbo natale segreto! ❄️
'''.format('la brava' if is_female(name) else 'il bravo', name), '''
Lascia che ti riepiloghi le regole:
👉 Ti chiederò alcuni dati
👉 Il giorno 16/12 estrarrò una persona a cui dovrai fare un regalo!
👉 Potrai scegliere il regalo tra quelli della sua wishlist Amazon
        ''', '''
Direi che ci siamo. Inizia con /set_list 😉!
        '''
    ]
    send_batch(update, to_send)
    set_status(user, None)


def set_list(bot, update):
    to_send = [
        '''
Benissimo, se non l'hai ancora fatto vai su https://www.amazon.it/gp/registry/wishlist/ e crea una wishlist.
Ricorda che deve essere pubblica! Una volta inseriti i prodotti torna su quella pagina e premi <i>Invia la lista ad altri</i>.
Copia il link che ti viene fornito, sarà del tipo <b>http://amzn.eu/abc1z23</b>.
        ''', '''
Io sono pronto! Mandami il link della tua wishlist Amazon.
        '''
    ]
    send_batch(update, to_send)
    set_status(update.message.from_user, 'WAIT_WISHLIST')


def got_wishlist(bot, update):
    entities = update.message.entities
    if len(entities) != 1:
        update.message.reply_text(
            'Non sono riuscito a trovare un link valido, scusa! Puoi riprovare?'
        )
        return
    link = update.message.parse_entity(entities[0])
    if not ('amazon' in link or 'amzn' in link):
        update.message.reply_text(
            'Non sono riuscito a trovare un link valido, scusa! Puoi riprovare?'
        )
    user = update.message.from_user
    store_list(user, link)
    update.message.reply_text('''
Fatto! Ho salvato la tua wishlist: {}

Potrebbe essere un ottimo momento per impostare il tuo indirizzo con /set_address!
    '''.format(link))
    set_status(user, None)
    send_completed(update)


def set_address(bot, update):
    to_send = [
        '''
Bene, avrò bisogno dell'indirizzo di spedizione per il tuo regalo. Assicurati di inserirlo correttamente!
Mandamelo con un messaggio simile a questo:
        ''', '''
Santa Claus
via delle Renne 1/B, Polo Nord 55041 (PN)

Altre note:
C/O Elfi Schiavizzati s.r.l.
        ''', '''
Quando vuoi, io sono pronto!
        '''
    ]
    send_batch(update, to_send)
    set_status(update.message.from_user, 'WAIT_ADDRESS')


def got_address(bot, update):
    txt = update.message.text
    user = update.message.from_user
    store_addr(user, txt)
    update.message.reply_text(
        'Fatto! Ho salvato il tuo messaggio:\n\n{}'.format(txt))
    set_status(user, None)
    send_completed(update)


def default(bot, update):
    user = update.message.from_user
    if not is_registered(user):
        update.message.reply_text('Hai bisogno di aiuto? Prova /start')
        return
    status = get_status(user)
    if status == 'WAIT_WISHLIST':
        got_wishlist(bot, update)
    elif status == 'WAIT_ADDRESS':
        got_address(bot, update)
    else:
        update.message.reply_text('Hai bisogno di aiuto? Prova /start')


# Basic bot structure


def error(bot, update, error):
    """Log Errors caused by Updates."""
    bot.send_message(admin, update)
    bot.send_message(admin, error)
    logger.warning('Update "%s" caused error "%s"', update, error)


def main():
    """Start the bot."""
    updater = Updater(TOKEN)
    j = updater.job_queue
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('set_list', set_list))
    dp.add_handler(CommandHandler('set_address', set_address))
    dp.add_handler(MessageHandler(Filters.text, default))
    dp.add_error_handler(error)

    j.run_once(alert, ALERT_DATE)
    j.run_once(draw_matches, DRAW_DATE)

    # Start
    if WEBHOOK_URL:
        logger.info("Running in webhook mode")
        updater.start_webhook(listen="0.0.0.0", port=443, url_path=TOKEN)
        updater.bot.set_webhook(WEBHOOK_URL + TOKEN)
    else:
        logger.info("Running in long-polling mode")
        updater.start_polling()

    updater.idle()
    logger.info("Closing shelve")
    db.close()


if __name__ == '__main__':
    main()
