import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Date, Time, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from data import groups_list, subjects_list
Base = declarative_base()

# TODO: потом рассмотреть возможность добавления модели студента
load_dotenv()

DB_URL = os.getenv("DB_URL")

class Group(Base):
    __tablename__ = 'group'
    group_id = Column(Integer, primary_key=True)
    group_name = Column(String, unique=True)
    # TODO: если будет добавлена модель студента, здесь создать связь (либо от студента к группе)

class Teacher(Base):
    __tablename__ = 'teachers'
    teacher_id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    # TODO: добавить больше информации о преподавателе(имейл, номер телефона)

class Subject(Base):
    __tablename__ = 'subjects'
    subject_id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)

class Lesson(Base):
    __tablename__ = 'lessons'
    lesson_id = Column(Integer, primary_key=True)
    start_datetime = Column(DateTime)
    end_datetime = Column(DateTime)
    group_id = Column(Integer, ForeignKey('group.group_id'))
    group = relationship('Group')
    teacher_id = Column(Integer, ForeignKey('teachers.teacher_id'))
    teacher = relationship('Teacher')
    classroom = Column(String)
    subject_id = Column(Integer, ForeignKey('subjects.subject_id'))
    subject = relationship('Subject')
    lesson_type = Column(String)


engine = create_engine(DB_URL)


def init_sync_db():
    Base.metadata.create_all(engine)

# FIXME: Решить проблему с асинхронными/синхронными БД

Session = sessionmaker(bind=engine)
session = Session()

# Автодобавление части данных
# groups = [Group(group_name=group) for group in groups_list]
# subjects = [Subject(name=subject) for subject in subjects_list]
#
# session.add_all(groups)
# session.add_all(subjects)
# session.commit()
