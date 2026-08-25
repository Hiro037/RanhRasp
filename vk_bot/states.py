from vkbottle import BaseStateGroup

class VkRegistrationStates(BaseStateGroup):
    WAITING_FOR_ROLE = "waiting_for_role"
    WAITING_FOR_GROUP = "waiting_for_group"
    WAITING_FOR_FORMAT = "waiting_for_format"
    WAITING_FOR_NOTIFICATIONS = "waiting_for_notifications"
    WAITING_FOR_TEACHER_NAME = "waiting_for_teacher_name"

class VkTeacherStates(BaseStateGroup):
    WAITING_FOR_COMMENT = "waiting_for_comment"
    