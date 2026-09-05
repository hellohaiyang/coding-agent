"""
ManagerSQLite。
每个模块对应一个数据库。

用法：
1.创建连接 module_sqlite=ManagerSQLite("test.db")
2.写操作 module_sqlite.execute_sql_write(“insert into...")
3.读操作 result=module_sqlite.execute_sql_read(“select * from...")
4.关闭服务 module_sqlite.close()
"""

import sqlite3


class ManagerSQLite:
    def __init__(self, db_name):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()

    def execute_sql_write(self, sql, params=()):
        self.cursor.execute(sql, params)
        self.conn.commit()

    def execute_sql_read(self, sql, params=()):
        self.cursor.execute(sql, params)
        return self.cursor.fetchall()


    def close(self):
        self.cursor.close()
        self.conn.close()
