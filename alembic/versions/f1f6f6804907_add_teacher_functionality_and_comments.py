"""add_teacher_functionality_and_comments

Revision ID: f1f6f6804907
Revises: 7cd98df2ea56
Create Date: 2025-12-27 22:24:38.718155

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'f1f6f6804907'
down_revision: Union[str, Sequence[str], None] = '7cd98df2ea56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()
    
    # Создаем lesson_comments только если её нет
    if 'lesson_comments' not in existing_tables:
        op.create_table('lesson_comments',
            sa.Column('comment_id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('lesson_id', sa.Integer(), nullable=False),
            sa.Column('teacher_id', sa.Integer(), nullable=False),
            sa.Column('comment_text', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, comment='Комментарий активен и виден студентам'),
            sa.ForeignKeyConstraint(['lesson_id'], ['lessons.lesson_id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['teacher_id'], ['teachers.teacher_id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('comment_id')
        )
        op.create_index(op.f('ix_lesson_comments_created_at'), 'lesson_comments', ['created_at'], unique=False)
        op.create_index(op.f('ix_lesson_comments_lesson_id'), 'lesson_comments', ['lesson_id'], unique=False)
        op.create_index(op.f('ix_lesson_comments_teacher_id'), 'lesson_comments', ['teacher_id'], unique=False)
    
    # Получаем существующие колонки таблицы users
    existing_columns = [col['name'] for col in inspector.get_columns('users')]
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('users')]
    
    # Используем batch mode для SQLite
    with op.batch_alter_table('users', schema=None) as batch_op:
        # Добавляем колонки только если их нет
        if 'user_type' not in existing_columns:
            batch_op.add_column(sa.Column('user_type', sa.String(length=20), server_default='student', nullable=False, comment='Тип: student или teacher'))
        
        if 'teacher_id' not in existing_columns:
            batch_op.add_column(sa.Column('teacher_id', sa.Integer(), nullable=True, comment='Связь с преподавателем (если user_type=teacher)'))
        
        if 'is_verified' not in existing_columns:
            batch_op.add_column(sa.Column('is_verified', sa.Boolean(), server_default='0', nullable=False, comment='Верифицирован ли пользователь (для преподавателей)'))
        
        # Создаем индексы только если их нет
        if 'ix_users_teacher_id' not in existing_indexes:
            batch_op.create_index(batch_op.f('ix_users_teacher_id'), ['teacher_id'], unique=False)
        
        if 'ix_users_user_type' not in existing_indexes:
            batch_op.create_index(batch_op.f('ix_users_user_type'), ['user_type'], unique=False)
        
        # Проверяем существующие внешние ключи
        existing_fks = inspector.get_foreign_keys('users')
        fks_to_teachers = [fk for fk in existing_fks 
                           if fk.get('referred_table') == 'teachers' and 'teacher_id' in fk.get('constrained_columns', [])]
        
        # Создаем FK только если его нет
        if not fks_to_teachers and 'teacher_id' in [col['name'] for col in inspector.get_columns('users')]:
            batch_op.create_foreign_key('fk_users_teacher_id', 'teachers', ['teacher_id'], ['teacher_id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = inspect(bind)
    
    existing_columns = [col['name'] for col in inspector.get_columns('users')]
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('users')]
    
    # Используем batch mode для SQLite
    with op.batch_alter_table('users', schema=None) as batch_op:
        # Удаляем внешний ключ
        existing_fks = inspector.get_foreign_keys('users')
        fks_to_teachers = [fk for fk in existing_fks 
                           if fk.get('referred_table') == 'teachers' and 'teacher_id' in fk.get('constrained_columns', [])]
        for fk in fks_to_teachers:
            if fk.get('name'):
                batch_op.drop_constraint(fk['name'], type_='foreignkey')
        
        # Удаляем индексы
        if 'ix_users_user_type' in existing_indexes:
            batch_op.drop_index(batch_op.f('ix_users_user_type'))
        if 'ix_users_teacher_id' in existing_indexes:
            batch_op.drop_index(batch_op.f('ix_users_teacher_id'))
        
        # Удаляем колонки
        if 'is_verified' in existing_columns:
            batch_op.drop_column('is_verified')
        if 'teacher_id' in existing_columns:
            batch_op.drop_column('teacher_id')
        if 'user_type' in existing_columns:
            batch_op.drop_column('user_type')
    
    # Удаляем таблицу lesson_comments
    if 'lesson_comments' in inspector.get_table_names():
        lesson_indexes = [idx['name'] for idx in inspector.get_indexes('lesson_comments')]
        if 'ix_lesson_comments_teacher_id' in lesson_indexes:
            op.drop_index(op.f('ix_lesson_comments_teacher_id'), table_name='lesson_comments')
        if 'ix_lesson_comments_lesson_id' in lesson_indexes:
            op.drop_index(op.f('ix_lesson_comments_lesson_id'), table_name='lesson_comments')
        if 'ix_lesson_comments_created_at' in lesson_indexes:
            op.drop_index(op.f('ix_lesson_comments_created_at'), table_name='lesson_comments')
        
        op.drop_table('lesson_comments')
