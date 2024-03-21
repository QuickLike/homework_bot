from http import HTTPStatus
import logging
import os
import sys
import time

from dotenv import load_dotenv
import requests
import telegram

from exceptions import HTTPStatusNotOK, RequestError


TOKENS_ERROR = 'Не валидные переменные окружения: {}!'
STATUS_VALUE_ERROR = 'Неожиданное значение ключа "status" - {}'
RESPONSE_NOT_DICT_ERROR = 'Объект HTTP-ответа должен быть словарем, вместо {}!'
HOMEWORKS_NOT_LIST_ERROR = 'Объект "homeworks" должен быть списком, вместо {}!'
HOMEWORKS_NOT_IN_DICT_ERROR = 'Ключ "homeworks" отсутствует в словаре!'
HOMEWORK_NAME_NOT_IN_DICT_ERROR = 'Ключ "homework_name" отсутсвует в словаре!'
RESPONSE_CODE_ERROR = '''Страница загружена с ошибками! Код страницы {0}.
                         Параметры запроса:
                         url: {1};
                         headers: {2};
                         params: {3}.'''
REQUEST_ERROR = '''Ошибка при подключении к странице {0}!
                   Параметры запроса:
                   headers: {1};
                   params: {2}.'''

STATUS_HAS_CHANGED = 'Изменился статус проверки работы "{0}". {1}'
SEND_MESSAGE_SUCCESS = 'Успешная отправка сообщения: {}.'


load_dotenv()

ENV_VARS = ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID')

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600

ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка токенов."""
    invalid_env_vars = [var for var in ENV_VARS if not globals().get(var)]
    if invalid_env_vars:
        logging.critical(TOKENS_ERROR.format(invalid_env_vars))
        raise ValueError(TOKENS_ERROR.format(invalid_env_vars))


def send_message(bot, message):
    """Отправка сообщения бота в Telegram."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except telegram.error.TelegramError as error:
        logging.error(error, exc_info=True)
    logging.debug(SEND_MESSAGE_SUCCESS.format(message))


def get_api_answer(timestamp):
    """Выполнение API-запроса."""
    params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp}
    }
    try:
        response = requests.get(**params)
    except requests.RequestException:
        raise RequestError(REQUEST_ERROR.format(
            params.get("url"),
            params.get("headers"),
            params.get("params")
        ))

    response_code = response.status_code
    if response_code != HTTPStatus.OK:
        raise HTTPStatusNotOK(RESPONSE_CODE_ERROR.format(
            response_code,
            params.get("url"),
            params.get("headers"),
            params.get("params")))
    json = response.json()
    for key in ['error', 'code']:
        if key in json:
            raise KeyError(f'JSON содержит {key}')
    return json


def check_response(response):
    """Проверка HTTP-ответа."""
    if not isinstance(response, dict):
        raise TypeError(RESPONSE_NOT_DICT_ERROR.format(type(response)))
    if 'homeworks' not in response:
        raise KeyError(HOMEWORKS_NOT_IN_DICT_ERROR)
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(HOMEWORKS_NOT_LIST_ERROR.format(type(homeworks)))
    return response


def parse_status(homework):
    """Получение статуса проверки домашнего задания."""
    status = homework['status']
    if 'homework_name' not in homework:
        raise KeyError(HOMEWORK_NAME_NOT_IN_DICT_ERROR)
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(STATUS_VALUE_ERROR.format(status))
    return STATUS_HAS_CHANGED.format(
        homework["homework_name"],
        HOMEWORK_VERDICTS[homework['status']]
    )


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)

    timestamp = int(time.time())
    current_verdict = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)['homeworks']
            if homeworks:
                verdict = parse_status(homeworks[0])
                if current_verdict != verdict:
                    verdict = parse_status(homeworks[0])
                    current_verdict = verdict
                    send_message(bot, verdict)
                    timestamp = response.get('current_date', timestamp)
                else:
                    logging.debug('Статус проверки не изменился')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message, exc_info=True)
            send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s, %(levelname)s, %(name)s, %(message)s',
        handlers=[logging.FileHandler(__file__ + '.log'),
                  logging.StreamHandler(sys.stdout)]
    )

    main()
