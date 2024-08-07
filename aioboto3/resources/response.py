from boto3.resources.response import RawHandler, ResourceHandler, build_identifiers, build_empty_response, all_not_none, jmespath


class AIOResourceHandler(ResourceHandler):
    async def __call__(self, parent, params, response):
        """
        :type parent: ServiceResource
        :param parent: The resource instance to which this action is attached.
        :type params: dict
        :param params: Request parameters sent to the service.
        :type response: dict
        :param response: Low-level operation response.
        """
        resource_name = self.resource_model.type
        json_definition = self.service_context.resource_json_definitions.get(
            resource_name
        )

        # Load the new resource class that will result from this action.
        resource_cls = await self.factory.load_from_definition(
            resource_name=resource_name,
            single_resource_json_definition=json_definition,
            service_context=self.service_context
        )
        raw_response = response
        search_response = None

        # Anytime a path is defined, it means the response contains the
        # resource's attributes, so resource_data gets set here. It
        # eventually ends up in resource.meta.data, which is where
        # the attribute properties look for data.
        if self.search_path:
            search_response = jmespath.search(self.search_path, raw_response)

        # First, we parse all the identifiers, then create the individual
        # response resources using them. Any identifiers that are lists
        # will have one item consumed from the front of the list for each
        # resource that is instantiated. Items which are not a list will
        # be set as the same value on each new resource instance.
        identifiers = dict(
            build_identifiers(
                self.resource_model.identifiers, parent, params, raw_response
            )
        )

        # If any of the identifiers is a list, then the response is plural
        plural = [v for v in identifiers.values() if isinstance(v, list)]

        if plural:
            response = []

            # The number of items in an identifier that is a list will
            # determine how many resource instances to create.
            for i in range(len(plural[0])):
                # Response item data is *only* available if a search path
                # was given. This prevents accidentally loading unrelated
                # data that may be in the response.
                response_item = None
                if search_response:
                    response_item = search_response[i]
                response.append(
                    self.handle_response_item(
                        resource_cls, parent, identifiers, response_item
                    )
                )
        elif all_not_none(identifiers.values()):
            # All identifiers must always exist, otherwise the resource
            # cannot be instantiated.
            response = self.handle_response_item(
                resource_cls, parent, identifiers, search_response
            )
        else:
            # The response should be empty, but that may mean an
            # empty dict, list, or None based on whether we make
            # a remote service call and what shape it is expected
            # to return.
            response = None
            if self.operation_name is not None:
                # A remote service call was made, so try and determine
                # its shape.
                response = build_empty_response(
                    self.search_path,
                    self.operation_name,
                    self.service_context.service_model
                )

        return response


class AIORawHandler(RawHandler):
    async def __call__(self, parent, params, response):
        return super(AIORawHandler, self).__call__(parent, params, response)
