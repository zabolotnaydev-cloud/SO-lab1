"""
console_demo.py — консольная версия примера TimerApp из методички, но на Python.

Три режима работы таймеров:
  1. Реагировать через определённый промежуток  -> «Прошло 5 секунд» (однократно)
  2. Реагировать в течение определённого времени -> звук каждые 2 с, но только 5 с
  3. Реагировать с указанным периодом            -> сам «звук» (scheduleAtFixedRate)
  + сообщение в точно заданный момент времени (schedule с datetime).

Запуск:  python console_demo.py
"""

import time
from datetime import datetime, timedelta

from timer_lib import Timer, TimerTask


class SoundPlayer(TimerTask):
    def run(self):
        print("\a", end="")                     # системный звуковой сигнал (beep)
        print(f"[{now()}] Звук воспроизведен")


class Message(TimerTask):
    def __init__(self, msg):
        super().__init__()
        self.msg = msg

    def run(self):
        print(f"[{now()}] {self.msg}")


class StopTimer(TimerTask):
    """Однократная задача, которая останавливает другой таймер."""
    def __init__(self, timer_to_stop, seconds):
        super().__init__()
        self.timer_to_stop = timer_to_stop
        self.seconds = seconds

    def run(self):
        print(f"[{now()}] Прошло {self.seconds} секунд")
        self.timer_to_stop.cancel()


def now():
    return datetime.now().strftime("%H:%M:%S")


def main():
    sound_timer = Timer("sound")
    message_timer = Timer("stopper")
    clock = Timer("clock")

    # Режим 3: с периодом — звук каждые 2 секунды (фиксированная частота)
    sound_timer.schedule_at_fixed_rate(SoundPlayer(), 0, 2)

    # Режим 1 + 2: через 5 секунд останавливаем звуковой таймер,
    # т.е. звук звучит только В ТЕЧЕНИЕ 5 секунд
    message_timer.schedule(StopTimer(sound_timer, 5), 5)

    # Сообщение в конкретный момент (в методичке — 18:24, здесь — через 7 с)
    alarm_at = datetime.now() + timedelta(seconds=7)
    clock.schedule(Message("Привет, привет, привет!!!"), alarm_at)

    print(f"[{now()}] Start (будильник на {alarm_at:%H:%M:%S})")

    time.sleep(8)                               # даём таймерам отработать
    for t in (sound_timer, message_timer, clock):
        t.cancel()
    print(f"[{now()}] Конец")


if __name__ == "__main__":
    main()
