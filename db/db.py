import asyncio
import configparser
from time import time
from datetime import datetime, timezone, timedelta

import openpyxl
import enum
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, \
    func, select, BigInteger, text, delete, and_, desc, join, UniqueConstraint, \
    Enum, Text
from sqlalchemy.orm import declarative_base, aliased, sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, \
    AsyncConnection
from sqlalchemy.dialects.postgresql import insert

from consts import T_RANGE_H
from consts.consts import LIMIT_STAT_NUMBERS, LIMIT_UPLOAD_EXCEL_LOG

config = configparser.ConfigParser()

config.read('../config.ini')

TYPE_DIALECT = config['DB']['type_dialect']
DB_USERNAME = config['DB']['db_username']
DB_PASSWORD = config['DB']['db_password']
DB_IP = config['DB']['db_ip']
DB_PORT = config['DB']['db_port']
DB_NAME = config['DB']['db_name']


Base = declarative_base()
POSTGRES_CONF = f'{TYPE_DIALECT}://{DB_USERNAME}:{DB_PASSWORD}@{DB_IP}:{DB_PORT}/{DB_NAME}'


async def create_async_engine_and_session():
    engine = create_async_engine(POSTGRES_CONF, echo=True)
    async_session = sessionmaker(bind=engine, class_=AsyncSession,
                                 expire_on_commit=False, autoflush=False)
    return engine, async_session


def connection_and_session(func):
    async def wrapper(*args, **kwargs):
        try:
            engine, async_session = await create_async_engine_and_session()

            async with engine.begin() as connection:
                async with async_session() as session:
                    return await func(connection, session, *args, **kwargs)

        except SQLAlchemyError as e:
            print(f'Произошла ошибка {e}')

    return wrapper


class CarStatus(enum.Enum):
    CHECK = 'check'


class CarNumber(Base):
    __tablename__ = 'car_numbers'

    id = Column(Integer, primary_key=True, autoincrement=True)
    number = Column(String(10), nullable=False)
    is_own = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=func.now())
    is_archive = Column(Boolean, default=False)
    status = Column(Enum(CarStatus), nullable=True)
    count_out_archive = Column(Integer, default=0)

    __table_args__ = (UniqueConstraint('number', name='unique_number'),)

    def __init__(self, auto_number, is_own=False,
                 is_archive=False, status=None):
        self.number = auto_number
        self.is_own = is_own
        self.is_archive = is_archive
        self.status = status


class LogHistory(Base):
    __tablename__ = 'log_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_user_id = Column(BigInteger, nullable=False, unique=True)
    car_number_id = Column(Integer, ForeignKey('car_numbers.id'))
    record_date = Column(DateTime, default=func.now())

    def __init__(self, tg_user_id, car_number_id):
        self.tg_user_id = tg_user_id
        self.car_number_id = car_number_id


class CarAction(enum.Enum):
    ADD = 'add'
    DELETE = 'delete'
    ARCHIVE = 'archive'


class AuditLog(Base):
    __tablename__ = 'audit_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_tg_id = Column(BigInteger, nullable=False)
    action = Column(Enum(CarAction), nullable=False)
    number = Column(String(10), nullable=False)
    timestamp = Column(DateTime, default=func.now())

    def __init__(self, actor_tg_id, action, number):
        self.actor_tg_id = actor_tg_id
        self.action = action
        self.number = number


class ExcelLog(Base):
    __tablename__ = 'excel_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_user_id = Column(BigInteger, nullable=False)
    added_numbers = Column(Text)
    deleted_numbers = Column(Text)
    timestamp = Column(DateTime, default=func.now())

    def __init__(self, tg_user_id, added_numbers, deleted_numbers):
        self.tg_user_id = tg_user_id
        self.added_numbers = added_numbers
        self.deleted_numbers = deleted_numbers


@connection_and_session
async def get_auto_number_id(connection: AsyncConnection,
                             session: AsyncSession,
                             auto_number) -> (int, bool):
    number = await session.execute(
        select(CarNumber).where(CarNumber.number == auto_number))
    number = number.scalar_one_or_none()
    if number:
        return number.id, number.is_own, number.is_archive
    return None, False, False


@connection_and_session
async def add_log_history(connection: AsyncConnection, session: AsyncSession,
                          tg_user_id, car_number_id) -> bool:
    existing_number = await session.execute(
        select(CarNumber).filter_by(id=car_number_id))
    existing_number = existing_number.scalar_one_or_none()
    if existing_number and existing_number.is_archive:
        existing_number.is_archive = False
        existing_number.count_out_archive += 1

    moscow_timezone = timezone(timedelta(hours=3))
    moscow_time = datetime.now(moscow_timezone)
    timestamp = moscow_time.timestamp()
    query = (
        select(
            func.EXTRACT('epoch', LogHistory.record_date)).where(
            LogHistory.car_number_id == car_number_id
        ).order_by(desc(LogHistory.record_date)).limit(1)
    )
    last_record = (await session.execute(query)).scalar_one_or_none()

    if (last_record is None or
            (isinstance(last_record, float) and (
                    int(timestamp) - last_record) / 3600 > (T_RANGE_H - 3))):
        log_history = LogHistory(tg_user_id, car_number_id)
        session.add(log_history)
        await session.commit()
        return True
    return False


@connection_and_session
async def add_auto_number(connection: AsyncConnection, session: AsyncSession,
                          auto_number, is_own):
    car = CarNumber(auto_number, is_own)
    session.add(car)
    await session.commit()
    return car.id


@connection_and_session
async def get_repeatable_parking(connection: AsyncConnection,
                                 session: AsyncSession, is_own: bool,
                                 is_archive: bool):
    car_numbers = CarNumber.__table__
    ranked_records_cte = (
        select(
            LogHistory.id,
            LogHistory.car_number_id,
            LogHistory.record_date
        )
        .cte('ranked_records')
    )
    repeatable_parking_cte = (
        select(
            ranked_records_cte.c.car_number_id,
            func.COUNT().label('parking_count')
        )
        .group_by(ranked_records_cte.c.car_number_id)
        .order_by(ranked_records_cte.c.car_number_id)
        .cte('repeatable_parking')
    )
    query = (
        select(
            car_numbers.c.id,
            car_numbers.c.number,
            car_numbers.c.is_own,
            repeatable_parking_cte.c.parking_count
        )
        .select_from(
            repeatable_parking_cte.outerjoin(
                car_numbers,
                car_numbers.c.id == repeatable_parking_cte.c.car_number_id
            )
        )
        .where(and_(car_numbers.c.is_own.is_(is_own),
                    car_numbers.c.is_archive.is_(is_archive)))
    ).order_by(desc(repeatable_parking_cte.c.parking_count)) \
        .order_by(desc(car_numbers.c.id))

    result = await session.execute(query)
    rows = result.fetchall()

    cars = []
    total_count = 0
    for row in rows:
        total_count += int(row.parking_count) if isinstance(row.parking_count,
                                                            int) else 0
        cars.append((row.number, row.parking_count))
    return cars, total_count


@connection_and_session
async def get_repeatable_parking_offset(connection: AsyncConnection,
                                        session: AsyncSession,
                                        is_own, is_archive, current, limit):
    start = (current - 1) * limit
    car_numbers = CarNumber.__table__
    ranked_records_cte = (
        select(
            LogHistory.id,
            LogHistory.car_number_id,
            LogHistory.record_date
        )
        .cte('ranked_records')
    )
    repeatable_parking_cte = (
        select(
            ranked_records_cte.c.car_number_id,
            func.COUNT().label('parking_count')
        )
        .group_by(ranked_records_cte.c.car_number_id)
        .order_by(ranked_records_cte.c.car_number_id)
        .cte('repeatable_parking')
    )
    query = (
        select(
            car_numbers.c.id,
            car_numbers.c.number,
            car_numbers.c.is_own,
            car_numbers.c.count_out_archive,
            repeatable_parking_cte.c.parking_count
        )
        .select_from(
            repeatable_parking_cte.outerjoin(
                car_numbers,
                car_numbers.c.id == repeatable_parking_cte.c.car_number_id
            )
        )
        .where(and_(car_numbers.c.is_own.is_(is_own),
                    car_numbers.c.is_archive.is_(is_archive)))
    ).order_by(desc(repeatable_parking_cte.c.parking_count)) \
        .order_by(desc(car_numbers.c.id))

    result = await session.execute(query.offset(start).limit(limit))
    rows = result.fetchall()

    cars = []
    for row in rows:
        cars.append((row.number, row.parking_count, row.count_out_archive))
    return cars


@connection_and_session
async def get_stat_numbers(connection: AsyncConnection, session: AsyncSession,
                           current=1, limit=LIMIT_STAT_NUMBERS):
    start = (current - 1) * limit
    date_format = func.to_char(LogHistory.record_date, 'YYYYMMDD').label(
        'full_date')

    subquery = (
        select(date_format, func.count().label('count_number'))
        .group_by(date_format)
        .order_by(desc(date_format))
    )

    result = await session.execute(subquery.offset(start).limit(limit))
    rows = result.fetchall()

    total_count = await session.scalar(func.count().select().
                                       select_from(LogHistory))

    data = [(datetime.strptime(row.full_date, '%Y%m%d').strftime(
        '%d.%m.%Y'), row.count_number) for row in rows]
    return data, total_count


@connection_and_session
async def get_stat_numbers_dates_count(
        connection: AsyncConnection,
        session: AsyncSession):
    date_format = func.to_char(LogHistory.record_date, 'YYYYMMDD').label(
        'full_date')

    query = (select(date_format)).group_by(date_format)
    result = await session.execute(query)
    count_record = result.fetchall()

    print(count_record)
    return len(count_record)


@connection_and_session
async def get_general_activity(connection: AsyncConnection,
                               session: AsyncSession):
    query = (
        select(LogHistory.tg_user_id, func.count().label("count"))
        .group_by(LogHistory.tg_user_id).order_by(desc("count"))
    )
    result = await session.execute(query)
    rows = result.fetchall()
    users = []
    for row in rows:
        users.append((row[0], row[1]))

    return users


@connection_and_session
async def get_general_activity_offset(connection: AsyncConnection,
                                      session: AsyncSession,
                                      current, limit):
    start = (current - 1) * limit

    query = (
        select(LogHistory.tg_user_id, func.count().label("count"))
        .group_by(LogHistory.tg_user_id).order_by(desc("count"))
    )
    result = await session.execute(query.offset(start).limit(limit))
    rows = result.fetchall()
    users = []
    for row in rows:
        users.append((row[0], row[1]))

    return users


@connection_and_session
async def get_active_users(connection: AsyncConnection, session: AsyncSession):
    query = (select(LogHistory.tg_user_id).group_by(LogHistory.tg_user_id))
    result = await session.execute(query)
    rows = result.fetchall()
    users = []
    for row in rows:
        users.append(row[0])

    return users


@connection_and_session
async def get_end_day_stats(connection: AsyncConnection,
                            session: AsyncSession):
    cte = text("""
        WITH daily_counts AS (
            SELECT
                date_trunc('day', lh.record_date) AS my_day,
                COUNT(*) AS record_count,
                0 AS plate_numbers_count
            FROM log_history lh
            GROUP BY my_day

            UNION ALL

            SELECT
                date_trunc('day', lh.record_date) AS my_day,
                0 AS record_count,
                COUNT(*) AS plate_numbers_count
            FROM log_history lh
            LEFT JOIN car_numbers cn ON cn.id = lh.car_number_id
            WHERE cn.is_own IS FALSE
            GROUP BY my_day
        )
        SELECT to_char(my_day, 'DD.MM.YYYY') my_day, SUM(record_count) AS total_plate_numbers, SUM(plate_numbers_count) AS other_plate_numbers
        FROM daily_counts
        GROUP BY my_day
        HAVING my_day = (
            SELECT my_day
            FROM daily_counts
            ORDER BY my_day DESC
            LIMIT 1
        )
        UNION ALL
        SELECT NULL AS my_day, COUNT(*) AS total_records_count, 0 AS total_plate_numbers_count
        FROM log_history lh2;
    """)

    result = await session.execute(cte)
    rows = result.fetchall()
    value = rows[0]
    day, total_plate_numbers_day, other_plate_numbers = value
    total_plate_numbers = rows[-1][1]

    current_day = (datetime.now()).strftime('%d.%m.%Y')

    if day and total_plate_numbers_day and (other_plate_numbers or other_plate_numbers == 0) and total_plate_numbers:
        if current_day != day:
            return current_day, '0', total_plate_numbers, '0'
        return day, total_plate_numbers_day, total_plate_numbers, other_plate_numbers

    return '0', '0', '0', '0'


@connection_and_session
async def get_number_detail(connection: AsyncConnection, session: AsyncSession,
                            search_number):
    stmt = select(
        text(
            "to_char(log_history.record_date, 'YYYYMMDD HH24:MI:SS') as fixed_date")
    ).select_from(LogHistory).outerjoin(CarNumber,
                                        CarNumber.id == LogHistory.car_number_id).filter(
        CarNumber.number == search_number
    ).order_by(text('fixed_date DESC'))

    result = await session.execute(stmt)

    dates = result.fetchall()

    data_r = [datetime.strptime(row[0], '%Y%m%d %H:%M:%S').strftime(
        '%d.%m.%Y %H:%M:%S') for row in dates]

    return data_r


@connection_and_session
async def get_number_detail_info_change(connection: AsyncConnection,
                                        session: AsyncSession, plate_number):
    date_format = func.to_char(AuditLog.timestamp,
                               'YYYYMMDD HH24:MI').label(
        'full_date')
    stmt = select(AuditLog.actor_tg_id, AuditLog.action, AuditLog.number,
                  date_format
                  ).select_from(AuditLog).filter_by(
        number=plate_number).order_by(text('full_date DESC'))
    result = await session.execute(stmt)
    audit_logs = result.fetchall()
    change_of_numbers = [(row[0], row[1], row[2],
               datetime.strptime(row[3], '%Y%m%d %H:%M').strftime(
                   '%d.%m.%Y %H:%M')) for row in audit_logs]
    return change_of_numbers


@connection_and_session
async def get_log_numbers_upload(connection: AsyncConnection,
                                 session: AsyncSession,
                                 cp=1,
                                 limit=LIMIT_UPLOAD_EXCEL_LOG):
    start = (cp - 1) * limit
    date_format = func.to_char(ExcelLog.timestamp,
                               'YYYYMMDD HH24:MI:SS').label(
        'full_date')
    stmt = select(ExcelLog.tg_user_id, ExcelLog.added_numbers,
                  ExcelLog.deleted_numbers,
                  date_format
                  ).select_from(ExcelLog).order_by(text('full_date DESC'))
    result = await session.execute(stmt.offset(start).limit(limit))
    excel_log = result.fetchall()
    log_uploaded_numbers = [(row[0], row[1], row[2],
                             datetime.strptime(row[3],
                                               '%Y%m%d %H:%M:%S').strftime(
                                 '%d.%m.%Y %H:%M:%S')) for row in excel_log]

    return log_uploaded_numbers


@connection_and_session
async def get_numbers_upload_count(connection: AsyncConnection,
                                   session: AsyncSession):
    return await session.scalar(func.count().select().
                                       select_from(ExcelLog))


@connection_and_session
async def is_exists_number_info_change(connection: AsyncConnection,
                                       session: AsyncSession,
                                       plate_number):
    stmt = select(AuditLog).filter_by(number=plate_number)
    result = await session.execute(stmt)
    audit_logs = result.fetchone()
    return audit_logs


@connection_and_session
async def is_in_archive_number(connection: AsyncConnection,
                               session: AsyncSession, search_number):
    stmt = select(CarNumber.is_archive).where(
        CarNumber.number == search_number)

    result = await session.execute(stmt)
    data = result.scalar_one_or_none()
    return data


@connection_and_session
async def set_archive_db(connection: AsyncConnection,
                         session: AsyncSession, tg_user_id, plate_number):
    existing_number = await session.execute(
        select(CarNumber).filter_by(number=plate_number))
    existing_number = existing_number.scalar_one_or_none()
    if existing_number:
        existing_number.is_own = False
        existing_number.is_archive = True
        new_audit_log = AuditLog(tg_user_id, CarAction.ARCHIVE, plate_number)
        session.add(new_audit_log)
        await session.commit()


@connection_and_session
async def update_plate_numbers_list(connection: AsyncConnection,
                                    session: AsyncSession, tg_user_id,
                                    values):
    numbers_to_update = await session.execute(
        select(CarNumber).filter(~CarNumber.number.in_(values))
    )

    current_numbers = [row[0].number for row in
                       await session.execute(select(CarNumber)
                                             .filter(CarNumber.is_own))]

    deleted_numbers = [number for number in current_numbers if
                       number not in values]
    added_numbers = [number for number in values if
                     number not in current_numbers]

    for del_number in deleted_numbers:
        existing_number = await session.execute(
            select(CarNumber).filter_by(number=del_number))
        existing_number = existing_number.scalar_one_or_none()
        if existing_number:
            existing_number.is_own = False
            existing_number.is_archive = True
            new_audit_log = AuditLog(tg_user_id, CarAction.DELETE, del_number)
            session.add(new_audit_log)
            # await session.commit()

    for add_number in added_numbers:
        existing_number = await session.execute(
            select(CarNumber).filter_by(number=add_number))
        existing_number = existing_number.scalar_one_or_none()
        if existing_number:
            existing_number.is_own = True
            if existing_number.is_archive:
                existing_number.count_out_archive += 1

            existing_number.is_archive = False
        else:
            new_car_number = CarNumber(add_number, is_own=True)
            session.add(new_car_number)

        new_audit_log = AuditLog(tg_user_id, CarAction.ADD, add_number)
        session.add(new_audit_log)

    del_numbers_formatted = ' '.join(deleted_numbers)
    add_numbers_formatted = ' '.join(added_numbers)
    new_log = ExcelLog(tg_user_id, add_numbers_formatted,
                       del_numbers_formatted)
    session.add(new_log)

    await session.commit()


async def main():
    engine = create_async_engine(POSTGRES_CONF,
                                 echo=True)
    async with engine.begin() as connection:
        async_session = sessionmaker(bind=engine, class_=AsyncSession,
                                     expire_on_commit=False, autoflush=False)
        async with async_session() as session:
            async with session.begin():
                await connection.run_sync(Base.metadata.create_all)
            print("База данных и таблицы успешно созданы")
    # await get_repeatable_parking(8, True)


if __name__ == '__main__':
    asyncio.run(main())
