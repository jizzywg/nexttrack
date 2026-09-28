from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from catalog.models import Track

from .engine import FEATURES
from .models import Feedback


class WeightsSerializer(serializers.Serializer):
    genre = serializers.FloatField(min_value=0, max_value=1, required=False)
    mood = serializers.FloatField(min_value=0, max_value=1, required=False)
    tempo = serializers.FloatField(min_value=0, max_value=1, required=False)
    decade = serializers.FloatField(min_value=0, max_value=1, required=False)


class RecommendationRequestSerializer(serializers.Serializer):
    seeds = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list, max_length=10
    )
    history = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list, max_length=50,
        help_text="Radio: tracks already played, oldest first. The last three become weighted seeds; all are excluded.",
    )
    k = serializers.IntegerField(min_value=1, max_value=50, default=10)
    weights = WeightsSerializer(required=False)
    aggregate = serializers.ChoiceField(choices=["mean", "max"], default="mean")
    diversity = serializers.FloatField(min_value=0.0, max_value=1.0, default=0.25)
    max_per_artist = serializers.IntegerField(min_value=1, max_value=10, default=2)
    exclude = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list, max_length=500
    )
    personalise = serializers.BooleanField(default=False)

    def validate(self, data):
        if not data.get("seeds") and not data.get("history"):
            raise serializers.ValidationError({"seeds": ["Give at least one seed track, a listening history, or both."]})
        return data

    def validate_weights(self, value):
        if value and sum(value.get(name, 0.0) for name in FEATURES) <= 0:
            raise serializers.ValidationError("At least one weight must be greater than zero.")
        return value


class BridgeRequestSerializer(serializers.Serializer):
    from_id = serializers.IntegerField(min_value=1)
    to_id = serializers.IntegerField(min_value=1)
    length = serializers.IntegerField(min_value=2, max_value=12, default=7)
    weights = WeightsSerializer(required=False)

    def validate(self, data):
        if data["from_id"] == data["to_id"]:
            raise serializers.ValidationError({"to_id": ["Pick a different track to the start."]})
        return data

    def validate_weights(self, value):
        if value and sum(value.get(name, 0.0) for name in FEATURES) <= 0:
            raise serializers.ValidationError("At least one weight must be greater than zero.")
        return value


class FeedbackSerializer(serializers.Serializer):
    track = serializers.PrimaryKeyRelatedField(queryset=Track.objects.all())
    value = serializers.ChoiceField(choices=[-1, 0, 1], help_text="1 = like, -1 = skip, 0 = clear")
    seeds = serializers.ListField(child=serializers.IntegerField(), required=False, default=list, max_length=10)


class FeedbackReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ["track", "value", "updated_at"]


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate_username(self, value):
        if get_user_model().objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("That username is taken.")
        return value

    def validate(self, attrs):
        user_model = get_user_model()
        candidate = user_model(username=attrs["username"], email=attrs.get("email", ""))
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs
