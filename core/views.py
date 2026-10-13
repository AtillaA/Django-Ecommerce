from functools import wraps

from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from requests import session
import stripe
from taggit.models import Tag
from core.models import Coupon, Product, Category, Vendor, CartOrder, CartOrderProducts, ProductImages, ProductReview, wishlist_model, Address
from userauths.models import ContactUs, Profile
from core.forms import ProductReviewForm
from core.cart import CART_SESSION_KEY, QUANTITY_ERROR, cart_line, cart_total, parse_quantity, refresh_cart
from core.payments import pay_order
from core.stock import OutOfStock, check_quantity, deduct_for_order
from django.template.loader import render_to_string
from django.contrib import messages

from django.urls import reverse
from django.conf import settings
from django.db import transaction
from django.views.decorators.http import require_POST
from paypal.standard.forms import PayPalPaymentsForm
from django.contrib.auth.decorators import login_required

from django.core.paginator import Paginator
from django.db.models import Avg, F
from django.core import serializers

def ajax_login_required(view):
    """login_required for AJAX endpoints: answer 401 so function.js sends the visitor to sign in."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, "Please sign in to continue.")
            return JsonResponse({"sign_in_url": reverse("userauths:sign-in")}, status=401)
        return view(request, *args, **kwargs)
    return wrapper


def index(request):
    # bannanas = Product.objects.all().order_by("-id")
    products = Product.objects.filter(product_status="published", featured=True).order_by("-id")

    context = {
        "products":products
    }

    return render(request, 'core/index.html', context)


# Shop page "Sort by" options: key -> (label, ordering)
PRODUCT_SORTS = {
    "featured": ("Featured", ["-featured", "-id"]),
    "price-asc": ("Price: Low to High", ["price", "-id"]),
    "price-desc": ("Price: High to Low", ["-price", "-id"]),
    "newest": ("Release Date", ["-date", "-id"]),
    "rating": ("Avg. Rating", [F("avg_rating").desc(nulls_last=True), "-id"]),
}
# Shop page "Show" options: products per page
PAGE_SIZES = ["50", "100", "150", "200", "all"]


def sort_products(products, sort):
    """Order products by a PRODUCT_SORTS key; unknown keys sort as Featured."""
    if sort not in PRODUCT_SORTS:
        sort = "featured"
    if sort == "rating":
        products = products.annotate(avg_rating=Avg("reviews__rating"))
    return products.order_by(*PRODUCT_SORTS[sort][1])


def product_list_view(request):
    sort = request.GET.get("sort") if request.GET.get("sort") in PRODUCT_SORTS else "featured"
    show = request.GET.get("show") if request.GET.get("show") in PAGE_SIZES else PAGE_SIZES[0]
    products = sort_products(Product.objects.filter(product_status="published"), sort)
    per_page = max(products.count(), 1) if show == "all" else int(show)
    page = Paginator(products, per_page).get_page(request.GET.get("page"))
    tags = Tag.objects.all().order_by("-id")[:6]

    def url_with(**changes):
        """This page's URL with some query parameters changed (back to page 1 unless page is given)."""
        params = request.GET.copy()
        params.pop("page", None)
        for key, value in changes.items():
            params[key] = value  # replaces; QueryDict.update() would append
        return f"?{params.urlencode()}"

    context = {
        "products": page,
        "page": page,
        "tags": tags,
        "sort_label": PRODUCT_SORTS[sort][0],
        "sort_options": [(label, url_with(sort=key), key == sort) for key, (label, _) in PRODUCT_SORTS.items()],
        "show_label": show.title(),
        "show_options": [(size.title(), url_with(show=size), size == show) for size in PAGE_SIZES],
        "page_links": [
            (number, None if number == page.paginator.ELLIPSIS else url_with(page=number), number == page.number)
            for number in page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1)
        ],
        "previous_url": url_with(page=page.previous_page_number()) if page.has_previous() else None,
        "next_url": url_with(page=page.next_page_number()) if page.has_next() else None,
    }

    return render(request, 'core/product-list.html', context)


def category_list_view(request):
    categories = Category.objects.all()

    context = {
        "categories":categories
    }
    return render(request, 'core/category-list.html', context)


def category_product_list__view(request, cid):

    category = get_object_or_404(Category, cid=cid)
    products = Product.objects.filter(product_status="published", category=category)

    context = {
        "category":category,
        "products":products,
    }
    return render(request, "core/category-product-list.html", context)


def vendor_list_view(request):
    vendors = Vendor.objects.all()
    context = {
        "vendors": vendors,
    }
    return render(request, "core/vendor-list.html", context)


def vendor_detail_view(request, vid):
    vendor = get_object_or_404(Vendor, vid=vid)
    products = Product.objects.filter(vendor=vendor, product_status="published").order_by("-id")

    context = {
        "vendor": vendor,
        "products": products,
    }
    return render(request, "core/vendor-detail.html", context)


def product_detail_view(request, pid):
    product = get_object_or_404(Product, pid=pid)
    products = Product.objects.filter(category=product.category, product_status="published").exclude(pid=pid)

    # Getting all reviews related to a product
    reviews = ProductReview.objects.filter(product=product).order_by("-date")

    # Getting average review
    average_rating = ProductReview.objects.filter(product=product).aggregate(rating=Avg('rating'))

    # Product Review form
    review_form = ProductReviewForm()


    make_review = True 

    if request.user.is_authenticated:
        user_review_count = ProductReview.objects.filter(user=request.user, product=product).count()

        if user_review_count > 0:
            make_review = False
    
    p_image = product.p_images.all()

    context = {
        "p": product,
        "make_review": make_review,
        "review_form": review_form,
        "p_image": p_image,
        "average_rating": average_rating,
        "reviews": reviews,
        "products": products,
    }

    return render(request, "core/product-detail.html", context)

def tag_list(request, tag_slug=None):

    products = Product.objects.filter(product_status="published").order_by("-id")

    tag = None 
    if tag_slug:
        tag = get_object_or_404(Tag, slug=tag_slug)
        products = products.filter(tags__in=[tag])

    context = {
        "products": products,
        "tag": tag
    }

    return render(request, "core/tag.html", context)


@ajax_login_required
def ajax_add_review(request, pid):
    product = get_object_or_404(Product, pk=pid)
    user = request.user 

    review = ProductReview.objects.create(
        user=user,
        product=product,
        review = request.POST['review'],
        rating = request.POST['rating'],
    )

    context = {
        'user': user.username,
        'review': request.POST['review'],
        'rating': request.POST['rating'],
    }

    average_reviews = ProductReview.objects.filter(product=product).aggregate(rating=Avg("rating"))

    return JsonResponse(
       {
         'bool': True,
        'context': context,
        'average_reviews': average_reviews
       }
    )


def search_view(request):
    query = request.GET.get("q", "")

    products = Product.objects.filter(title__icontains=query, product_status="published").order_by("-date")

    context = {
        "products": products,
        "query": query,
    }
    return render(request, "core/search.html", context)


def filter_product(request):
    categories = request.GET.getlist("category[]")
    vendors = request.GET.getlist("vendor[]")


    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')

    # Each filter narrows the list only when it has a value; with none, every product is shown.
    products = Product.objects.filter(product_status="published").order_by("-id").distinct()

    if min_price:
        products = products.filter(price__gte=min_price)
    if max_price:
        products = products.filter(price__lte=max_price)
    if categories:
        products = products.filter(category__id__in=categories)
    if vendors:
        products = products.filter(vendor__id__in=vendors)


    products = sort_products(products, request.GET.get("sort"))

    data = render_to_string("core/async/product-list.html", {"products": products})
    return JsonResponse({"data": data})


def add_to_cart(request):
    product_id = request.GET.get("id", "")
    if not product_id.isdigit():
        raise Http404
    product = get_object_or_404(Product, id=product_id, product_status="published")
    qty = parse_quantity(request.GET.get("qty", 1))
    if qty is None:
        return JsonResponse({"error": QUANTITY_ERROR}, status=400)

    cart = refresh_cart(request)
    if product_id in cart:
        qty += cart[product_id]["qty"]  # adding an item already in the cart adds to its quantity
    try:
        check_quantity(product, qty)
    except OutOfStock as error:
        return JsonResponse({"error": str(error)}, status=409)
    cart[product_id] = cart_line(product, qty)
    request.session[CART_SESSION_KEY] = cart
    return JsonResponse({"data": cart, 'totalcartitems': len(cart)})



def cart_view(request):
    if CART_SESSION_KEY in request.session:
        cart = refresh_cart(request)
        return render(request, "core/cart.html", {"cart_data": cart, 'totalcartitems': len(cart), 'cart_total_amount': cart_total(cart)})
    else:
        messages.warning(request, "Your cart is empty")
        return redirect("core:index")


def cart_fragment(request, cart, error=None, status=200):
    """The redrawn cart (core/async/cart-list.html) for function.js's redrawCart(), plus any error."""
    data = render_to_string("core/async/cart-list.html", {"cart_data": cart, 'totalcartitems': len(cart), 'cart_total_amount': cart_total(cart)}, request=request)
    response = {"data": data, 'totalcartitems': len(cart)}
    if error:
        response["error"] = error
    return JsonResponse(response, status=status)


def delete_item_from_cart(request):
    cart = refresh_cart(request)
    cart.pop(str(request.GET.get("id", "")), None)
    request.session[CART_SESSION_KEY] = cart
    return cart_fragment(request, cart)


def update_cart(request):
    cart = refresh_cart(request)
    product_id = str(request.GET.get("id", ""))
    qty = parse_quantity(request.GET.get("qty"))
    if qty is None:
        return cart_fragment(request, cart, error=QUANTITY_ERROR, status=400)

    if product_id in cart:
        product = Product.objects.get(id=product_id)
        try:
            check_quantity(product, qty)
        except OutOfStock as error:
            return cart_fragment(request, cart, error=str(error), status=409)
        cart[product_id] = cart_line(product, qty)
        request.session[CART_SESSION_KEY] = cart
    return cart_fragment(request, cart)


@login_required
def save_checkout_info(request):
    cart = refresh_cart(request)
    if request.method == "POST" and cart:
        # Stock may have changed since the items were added
        products = Product.objects.in_bulk([int(product_id) for product_id in cart])
        for product_id, item in cart.items():
            try:
                check_quantity(products[int(product_id)], item["qty"])
            except OutOfStock as error:
                messages.error(request, str(error))
                return redirect("core:cart")

        full_name = request.POST.get("full_name")
        email = request.POST.get("email")
        mobile = request.POST.get("mobile")
        address = request.POST.get("address")
        city = request.POST.get("city")
        state = request.POST.get("state")
        country = request.POST.get("country")

        print(full_name)
        print(email)
        print(mobile)
        print(address)
        print(city)
        print(state)
        print(country)

        request.session['full_name'] = full_name
        request.session['email'] = email
        request.session['mobile'] = mobile
        request.session['address'] = address
        request.session['city'] = city
        request.session['state'] = state
        request.session['country'] = country


        if cart:
            full_name = request.session['full_name']
            email = request.session['email']
            phone = request.session['mobile']
            address = request.session['address']
            city = request.session['city']
            state = request.session['state']
            country = request.session['country']

            # Create ORder Object
            order = CartOrder.objects.create(
                user=request.user,
                price=cart_total(cart),
                full_name=full_name,
                email=email,
                phone=phone,
                address=address,
                city=city,
                state=state,
                country=country,
            )

            del request.session['full_name']
            del request.session['email']
            del request.session['mobile']
            del request.session['address']
            del request.session['city']
            del request.session['state']
            del request.session['country']

            for p_id, item in cart.items():
                cart_order_products = CartOrderProducts.objects.create(
                    order=order,
                    product_id=int(p_id),
                    invoice_no="INVOICE_NO-" + str(order.id), # INVOICE_NO-5,
                    item=item['title'],
                    image=item['image'],
                    qty=item['qty'],
                    price=item['price'],
                    total=item['subtotal']
                )



        return redirect("core:checkout", order.oid)
    return redirect("core:cart")



@require_POST
@ajax_login_required
def create_checkout_session(request, oid):
    order = get_object_or_404(CartOrder, oid=oid, user=request.user)
    if order.paid_status:
        return JsonResponse({"error": "This order is already paid."}, status=400)
    stripe.api_key = settings.STRIPE_SECRET_KEY

    checkout_session = stripe.checkout.Session.create(
        customer_email = order.email,
        payment_method_types=['card'],
        line_items = [
            {
                'price_data': {
                    'currency': 'USD',
                    'product_data': {
                        'name': order.full_name
                    },
                    'unit_amount': int(order.price * 100)
                },
                'quantity': 1
            }
        ],
        mode = 'payment',
        success_url = request.build_absolute_uri(reverse("core:payment-completed", args=[order.oid])) + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url = request.build_absolute_uri(reverse("core:payment-completed", args=[order.oid]))
    )

    order.stripe_payment_intent = checkout_session['id']
    order.save()

    print("checkkout session", checkout_session)
    return JsonResponse({"sessionId": checkout_session.id})




@login_required
def checkout(request, oid):
    order = get_object_or_404(CartOrder, oid=oid, user=request.user)
    order_items = CartOrderProducts.objects.filter(order=order)

   
    if request.method == "POST":
        code = request.POST.get("code")
        print("code ========", code)
        coupon = Coupon.objects.filter(code=code, active=True).first()
        if coupon:
            if coupon in order.coupons.all():
                messages.warning(request, "Coupon already activated")
                return redirect("core:checkout", order.oid)
            else:
                discount = order.price * coupon.discount / 100 

                order.coupons.add(coupon)
                order.price -= discount
                order.saved += discount
                order.save()

                messages.success(request, "Coupon Activated")
                return redirect("core:checkout", order.oid)
        else:
            messages.error(request, "Coupon Does Not Exists")

        

    context = {
        "order": order,
        "order_items": order_items,
        "stripe_publishable_key": settings.STRIPE_PUBLIC_KEY,
        "payment_mock": settings.PAYMENT_MOCK,

    }
    return render(request, "core/checkout.html", context)


@login_required
def mock_payment(request, oid):
    if not settings.PAYMENT_MOCK:
        raise Http404
    order = get_object_or_404(CartOrder, oid=oid, user=request.user)

    # GET happens after a sign-in redirect; send the user back to the pay button.
    if request.method != "POST":
        return redirect("core:checkout", order.oid)

    # Stock comes off only when the payment goes through; all of it happens or none of it does.
    # Claiming the order with a conditional UPDATE first means a double-click can't pay twice.
    with transaction.atomic():
        if CartOrder.objects.filter(pk=order.pk, paid_status=False).update(paid_status=True):
            try:
                deduct_for_order(order)
            except OutOfStock as error:
                transaction.set_rollback(True)
                messages.error(request, str(error))
                return redirect("core:cart")
            payment = pay_order(order)
            if payment["status"] != "succeeded":
                transaction.set_rollback(True)
                return redirect("core:payment-failed")
            CartOrder.objects.filter(pk=order.pk).update(stripe_payment_intent=payment["id"])
            request.session.pop("cart_data_obj", None)

    return redirect("core:payment-completed", order.oid)


@login_required
def payment_completed_view(request, oid):
    order = get_object_or_404(CartOrder, oid=oid, user=request.user)

    if order.paid_status == False:
        # With mock payments only mock_payment marks orders paid.
        if settings.PAYMENT_MOCK:
            return redirect("core:checkout", order.oid)
        order.paid_status = True
        order.save()
        
    context = {
        "order": order,
        "stripe_publishable_key": settings.STRIPE_PUBLIC_KEY,

    }
    return render(request, 'core/payment-completed.html',  context)

@login_required
def payment_failed_view(request):
    return render(request, 'core/payment-failed.html')


@login_required
def customer_dashboard(request):
    orders_list = CartOrder.objects.filter(user=request.user).order_by("-id")
    address = Address.objects.filter(user=request.user)


    if request.method == "POST":
        address = request.POST.get("address")
        mobile = request.POST.get("mobile")

        new_address = Address.objects.create(
            user=request.user,
            address=address,
            mobile=mobile,
        )
        messages.success(request, "Address Added Successfully.")
        return redirect("core:dashboard")
    else:
        print("Error")
    
    user_profile = Profile.objects.get(user=request.user)
    print("user profile is: #########################",  user_profile)

    context = {
        "user_profile": user_profile,
        "orders_list": orders_list,
        "address": address,
    }
    return render(request, 'core/dashboard.html', context)

@login_required
def order_detail(request, id):
    order = get_object_or_404(CartOrder, user=request.user, id=id)
    order_items = CartOrderProducts.objects.filter(order=order)

    
    context = {
        "order_items": order_items,
    }
    return render(request, 'core/order-detail.html', context)


@ajax_login_required
def make_address_default(request):
    address = get_object_or_404(Address, id=request.GET['id'], user=request.user)
    Address.objects.filter(user=request.user).update(status=False)
    Address.objects.filter(id=address.id).update(status=True)
    return JsonResponse({"boolean": True})

@login_required
def wishlist_view(request):
    wishlist = wishlist_model.objects.filter(user=request.user)
    context = {
        "w":wishlist
    }
    return render(request, "core/wishlist.html", context)


    # w

@ajax_login_required
def add_to_wishlist(request):
    product_id = request.GET['id']
    product = get_object_or_404(Product, id=product_id)
    print("product id isssssssssssss:" + product_id)

    context = {}

    wishlist_count = wishlist_model.objects.filter(product=product, user=request.user).count()
    print(wishlist_count)

    if wishlist_count > 0:
        context = {
            "bool": True
        }
    else:
        new_wishlist = wishlist_model.objects.create(
            user=request.user,
            product=product,
        )
        context = {
            "bool": True
        }

    context["wishlist_count"] = wishlist_model.objects.filter(user=request.user).count()
    return JsonResponse(context)


# def remove_wishlist(request):
#     pid = request.GET['id']
#     wishlist = wishlist_model.objects.filter(user=request.user).values()

#     product = wishlist_model.objects.get(id=pid)
#     h = product.delete()

#     context = {
#         "bool": True,
#         "wishlist":wishlist
#     }
#     t = render_to_string("core/async/wishlist-list.html", context)
#     return JsonResponse({"data": t, "w":wishlist})

@ajax_login_required
def remove_wishlist(request):
    pid = request.GET['id']
    wishlist = wishlist_model.objects.filter(user=request.user)
    wishlist_d = get_object_or_404(wishlist_model, id=pid, user=request.user)
    delete_product = wishlist_d.delete()
    
    context = {
        "bool":True,
        "w":wishlist
    }
    wishlist_json = serializers.serialize('json', wishlist)
    t = render_to_string('core/async/wishlist-list.html', context)
    return JsonResponse({'data':t,'w':wishlist_json, 'wishlist_count': wishlist.count()})





# Other Pages 
def contact(request):
    return render(request, "core/contact.html")


def ajax_contact_form(request):
    full_name = request.GET['full_name']
    email = request.GET['email']
    phone = request.GET['phone']
    subject = request.GET['subject']
    message = request.GET['message']

    contact = ContactUs.objects.create(
        full_name=full_name,
        email=email,
        phone=phone,
        subject=subject,
        message=message,
    )

    data = {
        "bool": True,
        "message": "Message Sent Successfully"
    }

    return JsonResponse({"data":data})


def about_us(request):
    return render(request, "core/about_us.html")


def purchase_guide(request):
    return render(request, "core/purchase_guide.html")

def privacy_policy(request):
    return render(request, "core/privacy_policy.html")

def terms_of_service(request):
    return render(request, "core/terms_of_service.html")


