"""
app.py — графическое приложение (tkinter) с несколькими таймерами.

Каждый блок окна использует СВОЙ объект Timer:
  1. «Через промежуток»   — schedule(task, delay): одно срабатывание через N секунд.
  2. «В течение времени»  — scheduleAtFixedRate каждую 1 с + второй таймер,
                            который через N секунд останавливает первый (cancel).
  3. «С периодом»         — повтор с периодом; можно выбрать schedule (фикс. задержка)
                            или scheduleAtFixedRate (фикс. частота) и сравнить их.
  4. «Будильник»          — schedule(task, datetime): срабатывание в заданное время.

Важно: tkinter можно менять только из главного потока, а TimerTask.run()
выполняется в потоке таймера. Поэтому задачи не трогают окно напрямую,
а кладут функцию в очередь (self.post), которую главный поток
проверяет каждые 50 мс (метод _process_ui_queue).

Запуск:  python app.py
"""

import queue
import time
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk

from timer_lib import Timer, TimerTask


# ===================== Задачи (подклассы TimerTask) =====================

class CallbackTask(TimerTask):
    """Универсальная задача: при срабатывании передаёт функцию в GUI-поток."""
    def __init__(self, app, callback):
        super().__init__()
        self.app = app
        self.callback = callback

    def run(self):
        self.app.post(self.callback)


class PeriodicCounterTask(TimerTask):
    """Задача для режима 3. Может «тормозить», чтобы показать разницу режимов."""
    def __init__(self, app, slow_on_run=None):
        super().__init__()
        self.app = app
        self.count = 0
        self.slow_on_run = slow_on_run       # номер запуска, который выполнится медленно
        self.started = time.monotonic()

    def run(self):
        self.count += 1
        t = time.monotonic() - self.started
        n = self.count
        self.app.post(lambda: self.app.on_periodic_tick(n, t))
        if n == self.slow_on_run:
            time.sleep(2.5)                  # имитация долгой работы задачи


class StopperTask(TimerTask):
    """Однократная задача: останавливает другой таймер."""
    def __init__(self, app, timer_to_stop, callback):
        super().__init__()
        self.app = app
        self.timer_to_stop = timer_to_stop
        self.callback = callback

    def run(self):
        self.timer_to_stop.cancel()
        self.app.post(self.callback)


# ============================ Приложение ============================

class TimerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ЛР1 — Планирование процессов с помощью таймеров")
        self.resizable(False, False)

        self.ui_queue = queue.Queue()
        # Все таймеры приложения. Остановленный Timer повторно использовать нельзя,
        # поэтому при каждом запуске создаётся новый объект.
        self.timers = {"delay": None, "duration": None, "duration_stop": None,
                       "periodic": None, "alarm": None}

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(50, self._process_ui_queue)

    # ---------- связь потоков таймеров с GUI ----------

    def post(self, fn):
        """Вызывается из потока таймера: передать функцию в главный поток."""
        self.ui_queue.put(fn)

    def _process_ui_queue(self):
        while not self.ui_queue.empty():
            self.ui_queue.get_nowait()()
        self.after(50, self._process_ui_queue)

    def log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{datetime.now():%H:%M:%S}] {text}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _new_timer(self, key):
        """Остановить старый таймер этого блока и создать новый."""
        if self.timers[key]:
            self.timers[key].cancel()
        self.timers[key] = Timer(key)
        return self.timers[key]

    def _stop_timer(self, key):
        if self.timers[key]:
            self.timers[key].cancel()
            self.timers[key] = None

    # ---------- интерфейс ----------

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        root = ttk.Frame(self, padding=10)
        root.grid()

        # --- 1. Через промежуток времени ---
        f1 = ttk.LabelFrame(root, text="1. Реагировать через промежуток времени — schedule(task, delay)")
        f1.grid(row=0, column=0, sticky="ew", **pad)
        ttk.Label(f1, text="Задержка, с:").grid(row=0, column=0, **pad)
        self.delay_var = tk.IntVar(value=5)
        ttk.Spinbox(f1, from_=1, to=600, width=6, textvariable=self.delay_var).grid(row=0, column=1, **pad)
        ttk.Button(f1, text="Запустить", command=self.start_delay).grid(row=0, column=2, **pad)
        ttk.Button(f1, text="Отменить", command=self.cancel_delay).grid(row=0, column=3, **pad)
        self.delay_status = ttk.Label(f1, text="ожидание запуска", width=34)
        self.delay_status.grid(row=0, column=4, **pad)

        # --- 2. В течение времени ---
        f2 = ttk.LabelFrame(root, text="2. Реагировать в течение времени — scheduleAtFixedRate + cancel()")
        f2.grid(row=1, column=0, sticky="ew", **pad)
        ttk.Label(f2, text="Длительность, с:").grid(row=0, column=0, **pad)
        self.duration_var = tk.IntVar(value=10)
        ttk.Spinbox(f2, from_=1, to=600, width=6, textvariable=self.duration_var).grid(row=0, column=1, **pad)
        ttk.Button(f2, text="Запустить", command=self.start_duration).grid(row=0, column=2, **pad)
        self.progress = ttk.Progressbar(f2, length=260, maximum=10)
        self.progress.grid(row=0, column=3, **pad)
        self.duration_status = ttk.Label(f2, text="0 / 10 с", width=12)
        self.duration_status.grid(row=0, column=4, **pad)

        # --- 3. С указанным периодом ---
        f3 = ttk.LabelFrame(root, text="3. Реагировать с указанным периодом — schedule / scheduleAtFixedRate")
        f3.grid(row=2, column=0, sticky="ew", **pad)
        ttk.Label(f3, text="Период, с:").grid(row=0, column=0, **pad)
        self.period_var = tk.DoubleVar(value=1.0)
        ttk.Spinbox(f3, from_=0.2, to=60, increment=0.1, width=6,
                    textvariable=self.period_var).grid(row=0, column=1, **pad)
        self.mode_var = tk.StringVar(value="rate")
        ttk.Radiobutton(f3, text="фикс. частота", value="rate",
                        variable=self.mode_var).grid(row=0, column=2, **pad)
        ttk.Radiobutton(f3, text="фикс. задержка", value="delay",
                        variable=self.mode_var).grid(row=0, column=3, **pad)
        self.slow_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f3, text="3-й запуск «тормозит» 2.5 с",
                        variable=self.slow_var).grid(row=1, column=2, columnspan=2, sticky="w", **pad)
        ttk.Button(f3, text="Старт", command=self.start_periodic).grid(row=0, column=4, **pad)
        ttk.Button(f3, text="Стоп", command=self.stop_periodic).grid(row=1, column=4, **pad)
        self.counter_label = ttk.Label(f3, text="0", font=("TkDefaultFont", 20, "bold"), width=5,
                                       anchor="center")
        self.counter_label.grid(row=0, column=5, rowspan=2, **pad)

        # --- 4. Будильник ---
        f4 = ttk.LabelFrame(root, text="4. Срабатывание в заданный момент — schedule(task, datetime)")
        f4.grid(row=3, column=0, sticky="ew", **pad)
        ttk.Label(f4, text="Время (ЧЧ:ММ:СС):").grid(row=0, column=0, **pad)
        self.alarm_var = tk.StringVar(value=(datetime.now() + timedelta(minutes=1)).strftime("%H:%M:%S"))
        ttk.Entry(f4, width=10, textvariable=self.alarm_var).grid(row=0, column=1, **pad)
        ttk.Button(f4, text="Установить", command=self.start_alarm).grid(row=0, column=2, **pad)
        self.alarm_status = ttk.Label(f4, text="не установлен", width=40)
        self.alarm_status.grid(row=0, column=3, **pad)

        # --- Журнал ---
        f5 = ttk.LabelFrame(root, text="Журнал событий")
        f5.grid(row=4, column=0, sticky="ew", **pad)
        self.log_box = tk.Text(f5, height=10, width=92, state="disabled")
        self.log_box.grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(root, text="Остановить все таймеры", command=self.stop_all).grid(row=5, column=0, **pad)

    # ---------- 1. Через промежуток ----------

    def start_delay(self):
        seconds = self.delay_var.get()
        timer = self._new_timer("delay")
        timer.schedule(CallbackTask(self, self.on_delay_fired), seconds)
        self.delay_status.configure(text=f"сработает через {seconds} с...")
        self.log(f"[1] Таймер запущен: сработает через {seconds} с")

    def cancel_delay(self):
        self._stop_timer("delay")
        self.delay_status.configure(text="отменён")
        self.log("[1] Таймер отменён (cancel)")

    def on_delay_fired(self):
        self.bell()
        self.delay_status.configure(text=f"СРАБОТАЛ в {datetime.now():%H:%M:%S}")
        self.log(f"[1] Прошло {self.delay_var.get()} с — таймер сработал")
        self._stop_timer("delay")          # одноразовый таймер больше не нужен

    # ---------- 2. В течение времени ----------

    def start_duration(self):
        total = self.duration_var.get()
        self.elapsed = 0
        self.progress.configure(maximum=total, value=0)
        self.duration_status.configure(text=f"0 / {total} с")

        tick_timer = self._new_timer("duration")       # таймер №1 — тикает каждую секунду
        stop_timer = self._new_timer("duration_stop")  # таймер №2 — останавливает №1
        tick_timer.schedule_at_fixed_rate(CallbackTask(self, self.on_duration_tick), 1, 1)
        stop_timer.schedule(StopperTask(self, tick_timer, self.on_duration_end), total + 0.05)
        self.log(f"[2] Реагируем каждую секунду в течение {total} с")

    def on_duration_tick(self):
        self.elapsed += 1
        total = self.duration_var.get()
        self.progress.configure(value=self.elapsed)
        self.duration_status.configure(text=f"{self.elapsed} / {total} с")

    def on_duration_end(self):
        self.bell()
        self.log(f"[2] Прошло {self.duration_var.get()} с — второй таймер остановил первый")
        self._stop_timer("duration_stop")

    # ---------- 3. С периодом ----------

    def start_periodic(self):
        period = self.period_var.get()
        mode = self.mode_var.get()
        timer = self._new_timer("periodic")
        task = PeriodicCounterTask(self, slow_on_run=3 if self.slow_var.get() else None)
        if mode == "rate":
            timer.schedule_at_fixed_rate(task, 0, period)
            name = "scheduleAtFixedRate (фикс. частота)"
        else:
            timer.schedule(task, 0, period)
            name = "schedule (фикс. задержка)"
        self.counter_label.configure(text="0")
        self.log(f"[3] Период {period} с, режим: {name}")

    def stop_periodic(self):
        self._stop_timer("periodic")
        self.log("[3] Периодический таймер остановлен")

    def on_periodic_tick(self, n, t):
        self.counter_label.configure(text=str(n))
        self.log(f"[3] Запуск №{n} на {t:6.2f} с от старта")

    # ---------- 4. Будильник ----------

    def start_alarm(self):
        try:
            hms = datetime.strptime(self.alarm_var.get().strip(), "%H:%M:%S").time()
        except ValueError:
            self.alarm_status.configure(text="неверный формат, нужно ЧЧ:ММ:СС")
            return
        when = datetime.combine(datetime.now().date(), hms)
        if when <= datetime.now():
            when += timedelta(days=1)                  # время уже прошло — на завтра
        timer = self._new_timer("alarm")
        timer.schedule(CallbackTask(self, self.on_alarm), when)
        self.alarm_status.configure(text=f"установлен на {when:%d.%m %H:%M:%S}")
        self.log(f"[4] Будильник установлен на {when:%d.%m.%Y %H:%M:%S}")

    def on_alarm(self):
        self.bell()
        self.alarm_status.configure(text="ЗВЕНИТ! Время пришло")
        self.log("[4] Будильник: время пришло!")
        self._stop_timer("alarm")

    # ---------- общее ----------

    def stop_all(self):
        for key in self.timers:
            self._stop_timer(key)
        self.log("Все таймеры остановлены")

    def on_close(self):
        self.stop_all()
        self.destroy()


if __name__ == "__main__":
    TimerApp().mainloop()
