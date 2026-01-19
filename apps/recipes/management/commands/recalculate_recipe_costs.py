from django.core.management.base import BaseCommand
from django.db import transaction
from apps.recipes.models import Recipe
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Recalculate total_cost for all recipes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=str,
            help='Recalculate costs for recipes of a specific user (UUID)',
        )
        parser.add_argument(
            '--recipe-id',
            type=str,
            help='Recalculate cost for a specific recipe (UUID)',
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        recipe_id = options.get('recipe_id')

        # Build queryset
        queryset = Recipe.objects.all()

        if recipe_id:
            queryset = queryset.filter(id=recipe_id)
            self.stdout.write(f'Recalculating cost for recipe {recipe_id}...')
        elif user_id:
            queryset = queryset.filter(created_by_id=user_id)
            self.stdout.write(f'Recalculating costs for recipes by user {user_id}...')
        else:
            self.stdout.write('Recalculating costs for all recipes...')

        total_recipes = queryset.count()
        if total_recipes == 0:
            self.stdout.write(self.style.WARNING('No recipes found.'))
            return

        self.stdout.write(f'Found {total_recipes} recipe(s) to process.')

        success_count = 0
        error_count = 0

        for recipe in queryset.iterator():
            try:
                with transaction.atomic():
                    recipe.calculate_cost()
                    success_count += 1
                    if success_count % 100 == 0:
                        self.stdout.write(f'Processed {success_count}/{total_recipes} recipes...')
            except Exception as e:
                error_count += 1
                logger.error(f'Error calculating cost for recipe {recipe.id} ({recipe.name}): {str(e)}')
                self.stdout.write(
                    self.style.ERROR(f'Error processing recipe {recipe.id} ({recipe.name}): {str(e)}')
                )

        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS(f'Successfully processed: {success_count} recipes'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Failed: {error_count} recipes'))
        self.stdout.write('='*50)
