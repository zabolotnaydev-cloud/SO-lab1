"""
timer_lib.py — аналог java.util.Timer и java.util.TimerTask на Python.

Как и в Java:
  * TimerTask — абстрактное «действие»; нужно создать подкласс и
    переопределить метод run().
  * Timer — отдельный поток выполнения (thread), который хранит очередь
    запланированных задач и запускает их в нужный момент.
  * schedule()              — однократно или с ФИКСИРОВАННОЙ ЗАДЕРЖКОЙ
                              (следующий запуск = фактический старт предыдущего + period,
                              опоздание сдвигает все последующие запуски);
  * schedule_at_fixed_rate() — с ФИКСИРОВАННОЙ ЧАСТОТОЙ
                              (следующий запуск = ПЛАНОВОЕ время предыдущего + period,
                              опоздавшие запуски «догоняются»);
  * cancel()                 — останавливает таймер (или одну задачу).

Отличие от Java: время задаётся в СЕКУНДАХ (float), а не в миллисекундах.
Момент запуска можно передать как число секунд задержки или как datetime.
"""

import heapq
import itertools
import threading
import time
import traceback
from datetime import datetime


class TimerTask:
    """Действие, которое выполняет Timer. Переопределите run()."""

    def __init__(self):
        self._lock = threading.Lock()
        self._scheduled = False   # задача уже была передана таймеру
        self._cancelled = False   # задача отменена (или одноразовая уже выполнилась)
        self.period = 0.0         # 0 — однократно, >0 — fixed rate, <0 — fixed delay

    def run(self):
        raise NotImplementedError("Переопределите метод run() в подклассе")

    def cancel(self):
        """Отменяет задачу. Возвращает True, если это помешало будущим запускам."""
        with self._lock:
            will_run_again = self._scheduled and not self._cancelled
            self._cancelled = True
            return will_run_again

    @property
    def cancelled(self):
        return self._cancelled


class Timer:
    """Планировщик задач в отдельном потоке (один поток на один Timer)."""

    _ids = itertools.count(1)

    def __init__(self, name=None):
        self._queue = []                       # куча: (время_запуска, №, задача)
        self._order = itertools.count()        # для одинакового времени — порядок добавления
        self._cond = threading.Condition()     # пробуждение потока при изменении очереди
        self._cancelled = False
        self._thread = threading.Thread(
            target=self._main_loop,
            name=name or f"Timer-{next(Timer._ids)}",
            daemon=True,                       # не мешает завершению программы
        )
        self._thread.start()

    # ---------- публичный API (как в Java) ----------

    def schedule(self, task, when, period=None):
        """
        schedule(task, delay)          — один раз через delay секунд
        schedule(task, datetime)       — один раз в указанный момент
        schedule(task, delay, period)  — повторять с фиксированной ЗАДЕРЖКОЙ
        """
        if period is not None and period <= 0:
            raise ValueError("period должен быть > 0")
        self._add(task, self._to_delay(when), -period if period else 0.0)

    def schedule_at_fixed_rate(self, task, when, period):
        """Повторять с фиксированной ЧАСТОТОЙ (опоздавшие запуски «догоняются»)."""
        if period <= 0:
            raise ValueError("period должен быть > 0")
        self._add(task, self._to_delay(when), float(period))

    # Синоним с Java-названием, чтобы код совпадал с примерами из методички
    scheduleAtFixedRate = schedule_at_fixed_rate

    def cancel(self):
        """Останавливает таймер. После этого планировать задачи на нём нельзя."""
        with self._cond:
            self._cancelled = True
            self._queue.clear()
            self._cond.notify()

    @property
    def cancelled(self):
        return self._cancelled

    # ---------- внутренняя логика ----------

    @staticmethod
    def _to_delay(when):
        if isinstance(when, datetime):
            return max(0.0, (when - datetime.now()).total_seconds())
        if when < 0:
            raise ValueError("Отрицательная задержка")
        return float(when)

    def _add(self, task, delay, period):
        with self._cond:
            if self._cancelled:
                raise RuntimeError("Таймер уже остановлен (cancel)")
            with task._lock:
                if task._scheduled or task._cancelled:
                    raise RuntimeError("Задача уже запланирована или отменена")
                task._scheduled = True
                task.period = period
            run_at = time.monotonic() + delay
            heapq.heappush(self._queue, (run_at, next(self._order), task))
            self._cond.notify()                # разбудить поток: возможно, задача раньше прочих

    def _main_loop(self):
        while True:
            with self._cond:
                while not self._queue and not self._cancelled:
                    self._cond.wait()          # очередь пуста — спим
                if self._cancelled:
                    return

                run_at, _, task = self._queue[0]
                if task.cancelled:             # задачу отменили — выбрасываем
                    heapq.heappop(self._queue)
                    continue

                now = time.monotonic()
                if run_at > now:               # ещё рано — ждём (или пока не разбудят)
                    self._cond.wait(run_at - now)
                    continue

                heapq.heappop(self._queue)
                if task.period == 0:           # однократная — больше не запускаем
                    task._cancelled = True
                else:
                    next_run = (run_at + task.period if task.period > 0   # fixed rate
                                else now - task.period)                   # fixed delay
                    heapq.heappush(self._queue, (next_run, next(self._order), task))

            # run() выполняется ВНЕ блокировки, чтобы можно было вызвать cancel() изнутри
            try:
                task.run()
            except Exception:
                traceback.print_exc()
