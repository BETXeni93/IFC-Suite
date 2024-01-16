import time
import os

# from pympler import asizeof


class Logger:
    def __init__(self):
        # self.log_text = ""
        self.start_time = time.time()
        self.log_file = None
        self.output_folder = ""
        self.output_path = ""
        self.print_details = False
        self.no_output_file = False
        self.disabled = False

    def initiate_logfile(self, output_folder, print_details=False):
        if not self.no_output_file:
            self.start_time = time.time()
            self.output_folder = output_folder
            self.output_path = os.path.join(output_folder, "log.txt")
            self.log_file = open(
                self.output_path, "w", newline="", encoding="utf-8"
            )
            self.print_details = print_details

    def get_logfile_content(self):
        if not self.no_output_file:
            try:
                return self.log_file.read()
            except:
                with open(self.output_path, "r") as file:
                    return file.read()
        else:
            return "logfile disabled"

    def get_object_size(self, object):
        return "function deactivated"
        # size = asizeof.asizeof(object)
        # return f"size in bytes: {size}"

    def printlog(self, txt="", title=False):
        if self.disabled:
            return
        if not isinstance(txt, str):
            txt = str(txt)
        end_time = time.time()
        elapsed_time = end_time - self.start_time
        minutes, seconds = divmod(elapsed_time, 60)
        seconds, hundredths = divmod(seconds, 1)
        hundredths *= 100
        formatted_time = f"[{int(minutes):02}:{int(seconds):02}:{int(hundredths):02}]"

        if self.no_output_file:
            print(f"{formatted_time}  {txt}")
        else:
            separator = "-" * len(txt)
            if title:
                self.printlog()
                self.printlog(separator)
            print(f"{formatted_time}  {txt}")
            self.log_file.write(formatted_time + "  " + txt + "\n")
            self.log_file.flush()
            if title:
                self.printlog(separator)
                self.printlog()

    def printlog_details(self, txt="", title=False):
        if self.disabled:         
            return
        if not self.no_output_file:
            if self.print_details:
                self.printlog(txt, title)


    def close_log_file(self):
        if not self.no_output_file:
            self.printlog(f"Log file was saved to <{self.output_path}>")
            self.log_file.close()
            # with open(output_folder + "log.txt", "w", newline="", encoding="utf-8") as file:
            #     file.write(self.log_text)

