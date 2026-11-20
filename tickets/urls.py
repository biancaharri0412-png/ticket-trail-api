from rest_framework.routers import SimpleRouter

from .views import CategoryViewSet, TicketViewSet

router = SimpleRouter()
router.register("tickets", TicketViewSet, basename="ticket")
router.register("categories", CategoryViewSet, basename="category")

urlpatterns = router.urls