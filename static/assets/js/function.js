console.log("working fine");

const monthNames = ["Jan", "Feb", "Mar", "April", "May", "June",
    "July", "Aug", "Sept", "Oct", "Nov", "Dec"
];

$("#commentForm").submit(function (e) {
    e.preventDefault();

    let dt = new Date();
    let time = dt.getDay() + " " + monthNames[dt.getUTCMonth()] + ", " + dt.getFullYear()

    $.ajax({
        data: $(this).serialize(),

        method: $(this).attr("method"),

        url: $(this).attr("action"),

        dataType: "json",

        success: function (res) {
            console.log("Comment Saved to DB...");

            if (res.bool == true) {
                $("#review-res").html("Review added successfully.")
                $(".hide-comment-form").hide()
                $(".add-review").hide()

                let _html = '<div class="single-comment justify-content-between d-flex mb-30">'
                _html += '<div class="user justify-content-between d-flex">'
                _html += '<div class="thumb text-center">'
                _html += '<img src="https://thumbs.dreamstime.com/b/default-avatar-profile-vector-user-profile-default-avatar-profile-vector-user-profile-profile-179376714.jpg" alt="" />'
                _html += '<a href="#" class="font-heading text-brand">' + res.context.user + '</a>'
                _html += '</div>'

                _html += '<div class="desc">'
                _html += '<div class="d-flex justify-content-between mb-10">'
                _html += '<div class="d-flex align-items-center">'
                _html += '<span class="font-xs text-muted">' + time + ' </span>'
                _html += '</div>'

                for (var i = 1; i <= res.context.rating; i++) {
                    _html += '<i class="fas fa-star text-warning"></i>';
                }


                _html += '</div>'
                _html += '<p class="mb-10">' + res.context.review + '</p>'

                _html += '</div>'
                _html += '</div>'
                _html += ' </div>'

                $(".comment-list").prepend(_html)
            }


        }
    })
})



$(document).ready(function () {
    // Actions that need an account answer 401 for signed-out visitors: send them to sign in,
    // then back to this page.
    $(document).ajaxError(function (event, xhr) {
        if (xhr.status === 401 && xhr.responseJSON && xhr.responseJSON.sign_in_url) {
            window.location.href = xhr.responseJSON.sign_in_url + "?next=" + encodeURIComponent(window.location.pathname + window.location.search)
        }
    })

    $(".filter-checkbox, #price-filter-btn").on("click", function () {
        console.log("A checkbox have been clicked");

        let filter_object = {}

        let min_price = $("#max_price").attr("min")
        let max_price = $("#max_price").val()

        filter_object.min_price = min_price;
        filter_object.max_price = max_price;
        filter_object.sort = new URLSearchParams(window.location.search).get("sort") || "";  // keep the chosen "Sort by"

        $(".filter-checkbox").each(function () {
            let filter_value = $(this).val()
            let filter_key = $(this).data("filter") // vendor, category

            // console.log("Filter value is:", filter_value);
            // console.log("Filter key is:", filter_key);

            filter_object[filter_key] = Array.from(document.querySelectorAll('input[data-filter=' + filter_key + ']:checked')).map(function (element) {
                return element.value
            })
        })
        console.log("Filter Object is: ", filter_object);
        $.ajax({
            url: '/filter-products',
            data: filter_object,
            dataType: 'json',
            beforeSend: function () {
                console.log("Trying to filter product...");
            },
            success: function (response) {
                console.log(response.length);
                console.log("Data filtred successfully...");
                $(".totall-product").hide()
                $(".pagination-area").hide()  // filtered results come as one list
                $("#filtered-product").html(response.data)
            }
        })
    })

    $("#max_price").on("blur", function () {
        let min_price = $(this).attr("min")
        let max_price = $(this).attr("max")
        let current_price = $(this).val()

        // console.log("Current Price is:", current_price);
        // console.log("Max Price is:", max_price);
        // console.log("Min Price is:", min_price);

        if (current_price < parseInt(min_price) || current_price > parseInt(max_price)) {
            // console.log("Price Error Occured");

            min_price = Math.round(min_price * 100) / 100
            max_price = Math.round(max_price * 100) / 100


            // console.log("Max Price is:", min_Price);
            // console.log("Min Price is:", max_Price);

            alert("Price must between $" + min_price + ' and $' + max_price)
            $(this).val(min_price)
            $('#range').val(min_price)

            $(this).focus()

            return false

        }

    })

    // Add to cart functionality
    // Quantities are whole numbers of at least 1 (the server checks too)
    function validQuantity(value) {
        return /^\s*\d+\s*$/.test(value) && parseInt(value, 10) >= 1
    }

    // Shows the server's reason when it refuses a cart change (bad quantity, not enough stock)
    function showCartError(xhr) {
        if (xhr.responseJSON && xhr.responseJSON.error) {
            alert(xhr.responseJSON.error)
        }
    }


    // Delegated so buttons in lists redrawn by AJAX (e.g. the shop filter) work too.
    // Only the product ID and quantity are sent: the server takes title and price from the database.
    $(document).on("click", ".add-to-cart-btn", function () {

        let this_val = $(this)
        let index = this_val.attr("data-index")
        let quantity_input = $(".product-quantity-" + index)
        let quantity = quantity_input.val()

        if (!validQuantity(quantity)) {
            alert("Quantity must be a whole number of at least 1.")
            quantity_input.val(1)
            return
        }

        $.ajax({
            url: '/add-to-cart/',
            data: {
                'id': index,
                'qty': quantity,
            },
            dataType: 'json',
            success: function (response) {
                this_val.html("<i class='fas fa-check-circle'></i>")
                $(".cart-items-count").text(response.totalcartitems)
            },
            error: showCartError
        })
    })


    // Redraw the cart from the server's fragment, keeping what was typed in the checkout details
    function redrawCart(response) {
        let typed = $("#cart-list form").serializeArray()
        $("#cart-list").html(response.data)
        typed.forEach(function (field) {
            $("#cart-list form [name='" + field.name + "']").not("[type=hidden]").val(field.value)
        })
        $(".cart-items-count").text(response.totalcartitems)
    }


    // Cart handlers are delegated because redrawCart replaces the buttons
    $(document).on("click", ".delete-product", function () {

        let product_id = $(this).attr("data-product")
        let this_val = $(this)

        console.log("PRoduct ID:", product_id);

        $.ajax({
            url: "/delete-from-cart",
            data: {
                "id": product_id
            },
            dataType: "json",
            beforeSend: function () {
                this_val.hide()
            },
            success: function (response) {
                redrawCart(response)
            }
        })

    })




    $(document).on("click", ".update-product", function () {

        let product_id = $(this).attr("data-product")
        let this_val = $(this)
        let quantity_input = $(".product-qty-" + product_id)
        let product_quantity = quantity_input.val()

        if (!validQuantity(product_quantity)) {
            alert("Quantity must be a whole number of at least 1. Use the bin to remove an item.")
            quantity_input.val(quantity_input.prop("defaultValue"))
            return
        }

        $.ajax({
            url: "/update-cart/",
            data: {
                "id": product_id,
                "qty": product_quantity,
            },
            dataType: "json",
            beforeSend: function () {
                this_val.hide()
            },
            success: function (response) {
                redrawCart(response)
            },
            error: function (xhr) {
                // The server sends the unchanged cart with its reason; redraw it to undo the edit
                if (xhr.responseJSON && xhr.responseJSON.data) {
                    redrawCart(xhr.responseJSON)
                }
                this_val.show()
                showCartError(xhr)
            }
        })

    })


    // Making Default Address
    $(document).on("click", ".make-default-address", function () {
        let id = $(this).attr("data-address-id")
        let this_val = $(this)

        console.log("ID is:", id);
        console.log("Element is:", this_val);

        $.ajax({
            url: "/make-default-address",
            data: {
                "id": id
            },
            dataType: "json",
            success: function (response) {
                console.log("Address Made Default....");
                if (response.boolean == true) {

                    $(".check").hide()
                    $(".action_btn").show()

                    $(".check" + id).show()
                    $(".button" + id).hide()

                }
            }
        })
    })


    // Adding to wishlist
    $(document).on("click", ".add-to-wishlist", function () {
        let product_id = $(this).attr("data-product-item")
        let this_val = $(this)


        console.log("PRoduct ID IS", product_id);

        $.ajax({
            url: "/add-to-wishlist",
            data: {
                "id": product_id
            },
            dataType: "json",
            beforeSend: function () {
                console.log("Adding to wishlist...")
            },
            success: function (response) {
                // this_val.html("✓")
                this_val.html("<i class='fas fa-heart text-danger'></i>")
                $(".wishlist-items-count").text(response.wishlist_count)
                if (response.bool === true) {
                    console.log("Added to wishlist...");
                }
            }
        })
    })


    // Remove from wishlist
    $(document).on("click", ".delete-wishlist-product", function () {
        let wishlist_id = $(this).attr("data-wishlist-product")
        let this_val = $(this)

        console.log("wishlist id is:", wishlist_id);

        $.ajax({
            url: "/remove-from-wishlist",
            data: {
                "id": wishlist_id
            },
            dataType: "json",
            beforeSend: function () {
                console.log("Deleting product from wishlist...");
            },
            success: function (response) {
                $("#wishlist-list").html(response.data)
                $(".wishlist-items-count").text(response.wishlist_count)
            }
        })
    })


    $(document).on("submit", "#contact-form-ajax", function (e) {
        e.preventDefault()
        console.log("Submited...");

        let full_name = $("#full_name").val()
        let email = $("#email").val()
        let phone = $("#phone").val()
        let subject = $("#subject").val()
        let message = $("#message").val()

        console.log("Name:", full_name);
        console.log("Email:", email);
        console.log("Phone:", phone);
        console.log("Subject:", subject);
        console.log("MEssage:", message);

        $.ajax({
            url: "/ajax-contact-form",
            data: {
                "full_name": full_name,
                "email": email,
                "phone": phone,
                "subject": subject,
                "message": message,
            },
            dataType: "json",
            beforeSend: function () {
                console.log("Sending Data to Server...");
            },
            success: function (res) {
                console.log("Sent Data to server!");
                $(".contact_us_p").hide()
                $("#contact-form-ajax").hide()
                $("#message-response").html("Message sent successfully.")
            }
        })
    })




})







// // Add to cart functionality
// $(".add-to-cart-btn").on("click", function(){
//     let quantity = $("#product-quantity").val()
//     let product_title = $(".product-title").val()
//     let product_id = $(".product-id").val()
//     let product_price = $("#current-product-price").text()
//     let this_val = $(this)


//     console.log("Quantity:", quantity);
//     console.log("Title:", product_title);
//     console.log("Price:", product_price);
//     console.log("ID:", product_id);
//     console.log("Currrent Element:", this_val);

//     $.ajax({
//         url: '/add-to-cart',
//         data: {
//             'id': product_id,
//             'qty': quantity,
//             'title': product_title,
//             'price': product_price,
//         },
//         dataType: 'json',
//         beforeSend: function(){
//             console.log("Adding Product to Cart...");
//         },
//         success: function(response){
//             this_val.html("Item added to cart")
//             console.log("Added Product to Cart!");
//             $(".cart-items-count").text(response.totalcartitems)


//         }
//     })
// })